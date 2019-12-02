# Email bot
Are you an organized person? Do you like having everything in one place? Do you keep your calendar up-to-date? Do you enjoy your flight itineraries being automatically added to your Google Calendar. I like it too.

When you get an email about an event like a flight, concert, or restaurant reservation, it's added to your calendar automatically. But, have you noticed that not all booking confirmations are added automatically?

Being sports freak, I have been receiving numerous class confirmations from my local gym. None of them was picked by Google and parsed as a calendar event. Was it a big deal? No... but why shouldn't fix it anyway.


## Running the Project Locally
First, clone the repository to your local machine and install the requirements:

```bash
git clone https://github.com/sibtc/django-grouped-choice-field-example.git
conda env create -f path/to/environment.yml
```

Edit `personals.json` with your own data:

```json
{
  'blabla': 1
}
```

Run the app:

```bash
python email-bot.py
```

## Requirements
To create an app, we need a way to fetch emails from our Gmail account and a then to create events in Google Calendar.

Let's start with following code, see Google Developer documentation <https://developers.google.com/calendar/quickstart/python> and . Consider following imports to build a robust connection to Google API.
```python
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
```

First of all, the code try to establish connection with Google API. To do so, some credentials are required. If an app has been already authorized using OAuth and credentials are stored locally in a `token.pickle`, we load them and are good to go. Otherwise, a pop-up will open and we need to authorize an app to connect to our account.

```python
# If modifying these scopes, delete the file token.pickle.
SCOPES = [
  'https://www.googleapis.com/auth/gmail.readonly',
  'https://www.googleapis.com/auth/calendar.events'
]

def main():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
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
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('gmail', 'v1', credentials=creds)
```

Let's take some function predesigned in google api docs. The purpose of `ListMessagesMatchingQuery` is self-explanatory, it lists all Messages of the user's mailbox matching the query. Based in `user_id` and `msg_id` parameters `GetMimeMessage` get a Message object and use it to create a Multipurpose Internet Mail Extensions (MIME) message. MIME is an Internet standard that extends the format of email messages to support text in character sets other than ASCII, as well attachments of audio, video, images, and application programs. Message bodies may consist of multiple parts, and header information may be specified in non-ASCII character sets. Finally, to parse message body we take `text/plain` type and parse it with `get_payload_decode` function.

```python
def ListMessagesMatchingQuery(service, user_id, query=''):
    # ...
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

            if ctype == 'text/plain' and 'attachment' not in cdispo:
                body = part.get_payload(decode=True)  # decode
                break
    else:
        body = msg.get_payload(decode=True)
    return body.decode('utf-8')

def GetMimeMessage(service, user_id, msg_id):
    # ...
    try:
        message = service.users().messages().get(userId=user_id, id=msg_id,
                                                 format='raw').execute()

        print('Message snippet: %s' % message['snippet'])

        msg_str = base64.urlsafe_b64decode(message['raw'].encode('ASCII'))
        mime_msg = email.message_from_bytes(msg_str)

        return mime_msg
    except errors.HttpError as  error:
        print('An error occurred: %s' % error)
```

With helper functions in place we go back to main routine and list all messages' id and their textual content.

```python
def main():
    # ...
    messages = ListMessagesMatchingQuery(service,user_id='me',query='')

    for message in messages:
        msg = GetMimeMessage(service,user_id='me', msg_id = message['id'])
        print((message['id'],get_payload_decode(msg)))

if __name__ == '__main__':
    main()
```

Obviously, we don't want to list all messages, not really relevant, and not so efficient. Let's finally design some app specifics. Mails I receive from the gym are pretty straightforward, sender is always same, subject just states 'Potwierdzenie rezerwacji', Polish for booking confirmation. Class name is preceded by word 'zajęć', date is represented in `dd-mm-yyyy` format, time is `hh:mm`.

```python
def parse_yourgym(body):
    pattern = re.compile(r"zajęć (.*),.*(\d{2}-\d{2}-\d{4}).*(\d{2}:\d{2})")
    return pattern.findall(body)[0]

def main():
    # ...
    query = f"from:info@yourgym.pl subject:'Potwierdzenie rezerwacji'"
    messages = ListMessagesMatchingQuery(service,user_id='me',query=query)

    if messages:
        for message in messages:
            msg = GetMimeMessage(service,user_id='me', msg_id = message['id'])
            body = get_payload_decode(msg)

            if "yourgym" in body:
                event_fields = parse_yourgym(body)
                summary = event_fields[0]
                start_time = datetime.datetime.strptime(event_fields[1] + " " + event_fields[2] ,"%d-%m-%Y %H:%M")
                end_time = start_time + datetime.timedelta(minutes = 90)
```

create events

```python
def parse_yourgym(body):
    pattern = re.compile(r"zajęć (.*),.*(\d{2}-\d{2}-\d{4}).*(\d{2}:\d{2})")
    return pattern.findall(body)[0]

def main():
    # ...
    if messages:
        calendar_service = build('calendar', 'v3', credentials=creds)
        for message in messages:
            # ...
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
```

dont want to create same event all over again. save and query

```python
def main():
    # ...
    saved_events = {}
    if os.path.exists("events.pickle"):
        with open("events.pickle",'rb') as rfp:
            saved_events = pickle.load(rfp)

    after = "after:" + max([v['msg_time'] for k,v in saved_events.items()]).strftime("%Y/%m/%d") if len(saved_events) else ''
    query = f"from:zdrofitinfo@zdrofit.pl {after} subject:'Potwierdzenie rezerwacji'"

    # ...

    if messages:
      # ...
      for message in messages:
        # ...
        saved_events[message['id']] = {
            "msg_time": datetime.datetime.strptime(msg['Date'],"%a, %d %b %Y %H:%M:%S %z"),
            "event_id": event['id'],
            "event_time": start_time
        }

        with open("events.pickle",'wb') as wfp:
            pickle.dump(saved_events, wfp)
        # ...
```


## Conclustions
Further improvements: more sophisticated logic to parse emails
