import re

file_path = "c:\\AI-KIOSK\\knowledge_new\\admissions\\admissions.md"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# Fix common squashed patterns
text = text.replace("referhttps", "refer https")
text = text.replace("- PESU Merit QuotaVisithttps://admissions.pes.edu/to register for the entrance processSelect the program of choicePay the application fee and finish the full registrationBook your entrance slotPrint your entrance hall ticketAppear for the online interview process as per the information on your hall ticketEnsure to keep your educational transcripts and other supporting documents ready when you appear for the online interview process. This is mandatory.Results of the entrance process will be shared with the candidate within 3 working days from the date of completion of the online interview processIf selected, the email shared with the candidate will detail the process for admission, which starts with the payment of the blocking tuition fee.",
                    "- PESU Merit Quota: Visit https://admissions.pes.edu/ to register for the entrance process. Select the program of choice. Pay the application fee and finish the full registration. Book your entrance slot. Print your entrance hall ticket. Appear for the online interview process as per the information on your hall ticket. Ensure to keep your educational transcripts and other supporting documents ready when you appear for the online interview process. This is mandatory. Results of the entrance process will be shared with the candidate within 3 working days from the date of completion of the online interview process. If selected, the email shared with the candidate will detail the process for admission, which starts with the payment of the blocking tuition fee.")

text = text.replace("- PESU Merit QuotaVisithttps://admissions.pes.edu/to register for the entrance processSelect the program of choicePay the application fee and finish the full registrationBook your entrance slotPrint your entrance hall ticketAppear for the online interview process as per the information on your hall ticketEnsure to keep your educational transcripts and other supporting documents ready when you appear for the online interview process. This is mandatoryResults of the entrance process will be shared with the candidate within 3 working days from the date of completion of the online interview processIf selected, the email shared with the candidate will detail the process for admission, which starts with the payment of the blocking tuition fee.",
                    "- PESU Merit Quota: Visit https://admissions.pes.edu/ to register for the entrance process. Select the program of choice. Pay the application fee and finish the full registration. Book your entrance slot. Print your entrance hall ticket. Appear for the online interview process as per the information on your hall ticket. Ensure to keep your educational transcripts and other supporting documents ready when you appear for the online interview process. This is mandatory. Results of the entrance process will be shared with the candidate within 3 working days from the date of completion of the online interview process. If selected, the email shared with the candidate will detail the process for admission, which starts with the payment of the blocking tuition fee.")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Fixed admissions.md")
