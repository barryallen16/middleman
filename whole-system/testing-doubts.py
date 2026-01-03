import json
with open("./static/merged_credits.jsonl","r" , encoding="utf-8") as in_file:
    sub_code=[(json.loads(line))["subject_code"] for line in in_file]
for scode in sub_code:
    if scode[6]=="1":
        print(scode)