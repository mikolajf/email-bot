from __future__ import print_function
import base64
import datetime
import email
import json
import pickle
import re
import os.path
import time
from apiclient import errors
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from pdb import set_trace as bp

with open('personals.json','r') as f:
    personals = json.load(f)

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
'https://www.googleapis.com/auth/calendar.events']

def ListMessagesMatchingQuery(service, user_id, query=''):
  """List all Messages of the user's mailbox matching the query.

  Args:
    service: Authorized Gmail API service instance.
    user_id: User's email address. The special value "me"
    can be used to indicate the authenticated user.
    query: String used to filter messages returned.
    Eg.- 'from:user@some_domain.com' for Messages from a particular sender.

  Returns:
    List of Messages that match the criteria of the query. Note that the
    returned list contains Message IDs, you must use get with the
    appropriate ID to get the details of a Message.
  """
  try:
    response = service.users().messages().list(userId=user_id,
                                               q=query).execute()
    messages = []
    if 'messages' in response:
      messages.extend(response['messages'])

    while 'nextPageToken' in response:
      page_token = response['nextPageToken']
      response = service.users().messages().list(userId=user_id, q=query,
                                         pageToken=page_token).execute()
      messages.extend(response['messages'])

    return messages
  except errors.HttpError as error:
    print('An error occurred: %s' % error)

def get_payload_decode(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))

            # skip any text/plain (txt) attachments
            if ctype == 'text/plain' and 'attachment' not in cdispo:
                body = part.get_payload(decode=True)  # decode
                break
    # not multipart - i.e. plain text, no attachments, keeping fingers crossed
    else:
        body = msg.get_payload(decode=True)
    return body.decode('utf-8')

def GetMimeMessage(service, user_id, msg_id):
  """Get a Message and use it to create a MIME Message.

  Args:
    service: Authorized Gmail API service instance.
    user_id: User's email address. The special value "me"
    can be used to indicate the authenticated user.
    msg_id: The ID of the Message required.

  Returns:
    A MIME Message, consisting of data from Message.
  """
  try:
    message = service.users().messages().get(userId=user_id, id=msg_id,
                                             format='raw').execute()

    # print('Message snippet: %s' % message['snippet'])

    msg_str = base64.urlsafe_b64decode(message['raw'].encode('ASCII'))
    mime_msg = email.message_from_bytes(msg_str)

    return mime_msg
  except errors.HttpError as  error:
    print('An error occurred: %s' % error)

def parseZdrofit(body):
    pattern = re.compile(r"zajęć (.*),.*(\d{2}-\d{2}-\d{4}).*(\d{2}:\d{2})")
    return pattern.findall(body)[0]

def main():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    try:
        while True:
            service = build('gmail', 'v1', credentials=creds)

            # Call the Gmail API
            saved_events = {}
            if os.path.exists("events.pickle"):
                with open("events.pickle",'rb') as rfp: 
                    saved_events = pickle.load(rfp)

            after = "after:" + max([v['msg_time'] for k,v in saved_events.items()]).strftime("%Y/%m/%d") if len(saved_events) else ''

            query = f"from:zdrofitinfo@zdrofit.pl {after} subject:'Potwierdzenie rezerwacji'" 

            messages = ListMessagesMatchingQuery(service,user_id='me',query=query)

            messages = [message for message in messages if message['id'] not in saved_events.keys()]
            print(messages)

            if messages:
                calendar_service = build('calendar', 'v3', credentials=creds)

                for message in messages:
                    msg = GetMimeMessage(service,user_id='me', msg_id = message['id'])
                    body = get_payload_decode(msg)

                    if "Zdrofit" in body:
                        event_fields = parseZdrofit(body)
                        summary = event_fields[0]
                        start_time = datetime.datetime.strptime(event_fields[1] + " " + event_fields[2] ,"%d-%m-%Y %H:%M")
                        end_time = start_time + datetime.timedelta(minutes = 90)
                    # elif "Siatkówka" in body:
                    #     summary = event_fields[1]
                    #     start_time = datetime.datetime.strptime(event_fields[3] + " " + event_fields[2] ,"%Y-%m-%d %H:%M")
                    #     end_time = start_time + datetime.timedelta(minutes = 120)

                    if event_fields:
                        event = {
                            'summary': summary,
                            'start': {
                                'dateTime': start_time.isoformat("T"),
                                'timeZone': 'Europe/Warsaw',
                            },
                            'end': {
                                'dateTime': end_time.isoformat("T"),
                                'timeZone': 'Europe/Warsaw',
                            },
                            'reminders': {'useDefault': True},
                        }

                        event = calendar_service.events().insert(calendarId=personals['calendarId'], body=event).execute()
                        print(f"Calendar event id={event['id']} added: {summary} starting at {start_time.isoformat('T')}.")

                        saved_events[message['id']] = {
                            "msg_time": datetime.datetime.strptime(msg['Date'],"%a, %d %b %Y %H:%M:%S %z"),
                            "event_id": event['id'],
                            "event_time": start_time
                        }

                with open("events.pickle",'wb') as wfp:
                    pickle.dump(saved_events, wfp)

            else:
                print("No new mails.")

            time.sleep(5)

    except KeyboardInterrupt:
        print('Code interrupted!')

if __name__ == '__main__':
    main()

