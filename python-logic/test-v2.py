import json
filename="./static/grade-points.jsonl"
grade_points={}
with open(filename, 'r', encoding="utf-8") as in_file:
    for line in in_file:
        data=json.loads(line)
        grade_points[data['letter_grade']]=data['grade_points']

filename="./static/all-sub-v2.jsonl"
credits={}
with open(filename, 'r', encoding="utf-8") as in_file:
    for line in in_file:
        data=json.loads(line)
        credits[data['subject_code']] = data['credits']

acq_credits=0
total_credits=0

testfile="./static/test-marks.jsonl"
with open(testfile, 'r', encoding='utf-8')as file:
    for line in file:
        data= json.loads(line)
        # try:
        acq_credits+=grade_points[data['grade']] * credits[data['subject_code']]
        total_credits+=credits[data['subject_code']]
        # except KeyError:
        #     if '0' in data['subject_code']:                 
        #         acq_credits+=grade_points[data['grade']] * credits[data['subject_code'].replace('0','O')]
        #         total_credits+=credits[data['subject_code']]
        #     else:
        #         print('subject code not found.')
gpa = acq_credits / total_credits
print(f"Gpa is {gpa:.2f}")