import json
filename="./static/grade-points.jsonl"
grade_points={}
with open(filename, 'r', encoding="utf-8") as in_file:
    for line in in_file:
        data=json.loads(line)
        grade_points[data['letter_grade']]=data['grade_points']

acq_credits=0
total_credits=0

testfile="./static/test-marks.jsonl"
with open(testfile, 'r', encoding='utf-8')as file:
    for line in file:
        data= json.loads(line)
        acq_credits+=grade_points[data['grade']] * data['credits']
        total_credits+=data['credits']
gpa = acq_credits / total_credits
print(f"Gpa is {gpa:.2f}")