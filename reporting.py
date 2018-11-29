import smtplib

def get_gmail_server(gmail_user, gmail_pwd):
    smtpserver = smtplib.SMTP("smtp.gmail.com",587)
    smtpserver.ehlo()
    smtpserver.starttls()
    smtpserver.login(gmail_user, gmail_pwd)
    return smtpserver

def send_mail(smtpserver, gmail_user, to_address, subject, message):
    header = 'To:' + to_address + '\n' + 'From: Indian Kanoon<' + gmail_user + '>\n' + 'Subject: %s \n' % subject
    msg = header + '\n %s \n\n' % message
    smtpserver.sendmail(gmail_user, to_address, msg)

def report(gmail_user, gmail_pwd, to_addresses, subject, message):
    smtpserver = get_gmail_server(gmail_user, gmail_pwd)
    for address in to_addresses:
        send_mail(smtpserver, gmail_user, address, subject, message)
    smtpserver.close()

