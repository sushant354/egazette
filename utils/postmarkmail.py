from postmarker.core import PostmarkClient

def get_client(server_token):
    client = PostmarkClient(server_token = server_token)
    return client

def send_mail(client, from_addr, to_addr, subject, message):
    client.emails.send(
        From= from_addr,
        To=to_addr,
        Subject=subject,
        HtmlBody=message
    )

if __name__ == '__main__':
    import sys
    client = get_client(sys.argv[1])
    send_mail(client, 'IndianKanoon<admin@indiankanoon.com>' , 'sushant354@yahoo.com', 'Test Mail', 'Testing to see if email delivery works <a href="https://indiankanoon.org">Indian Kanoon Test</a>')
