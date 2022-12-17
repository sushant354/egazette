from . import postmarkmail

def report(server_token, from_addr, to_addresses, subject, message):
    client = postmarkmail.get_client(server_token)
    postmarkmail.send_mail(client, from_addr, to_addresses, subject, message)
