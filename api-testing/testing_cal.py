import json
import pandas as pd
test_dict=[{"student_regno": "221191101013", "student_name": "ALHAMEEM S", "results": [{"subject_code": "EBCC22I07", "grade": "B"}, {"subject_code": "EBCS22009", "grade": "C"}, {"subject_code": "EBCS22010", "grade": "C"}, {"subject_code": "EBCS22E11", "grade": "F"}, {"subject_code": "EBCS22L07", "grade": "S"}, {"subject_code": "EBCS22L08", "grade": "S"}, {"subject_code": "EBDS22ET6", "grade": "B"}, {"subject_code": "EBDS22I03", "grade": "B"}, {"subject_code": "EBDS22I04", "grade": "B"}, {"subject_code": "EBEE22OE6", "grade": "A"}, {"subject_code": "EBCS22006", "grade": "B"}, {"subject_code": "EBCS22007", "grade": "C"}]},
{"student_regno": "221191101047", "student_name": "ESHAA", "results": [{"subject_code": "EBCC22I07", "grade": "A"}, {"subject_code": "EBCS22009", "grade": "C"}, {"subject_code": "EBCS22010", "grade": "C"}, {"subject_code": "EBCS22E11", "grade": "F"}, {"subject_code": "EBCS22L07", "grade": "S"}, {"subject_code": "EBCS22L08", "grade": "S"}, {"subject_code": "EBDS22ET6", "grade": "B"}, {"subject_code": "EBDS22I03", "grade": "A"}, {"subject_code": "EBDS22I04", "grade": "S"}, {"subject_code": "EBEE22OE8", "grade": "B"}, {"subject_code": "EBBT22OE1", "grade": "A"}]},
{"student_regno": "221191101064", "student_name": "JAYADITHYA R", "results": [{"subject_code": "EBCC22I07", "grade": "S"}, {"subject_code": "EBCS22009", "grade": "A"}, {"subject_code": "EBCS22010", "grade": "A"}, {"subject_code": "EBCS22E11", "grade": "A"}, {"subject_code": "EBCS22L07", "grade": "H"}, {"subject_code": "EBCS22L08", "grade": "H"}, {"subject_code": "EBDS22ET6", "grade": "S"}, {"subject_code": "EBDS22I03", "grade": "H"}, {"subject_code": "EBDS22I04", "grade": "H"}, {"subject_code": "EBEC22OE2", "grade": "S"}]},
{"student_regno": "221191101088", "student_name": "MD TAQIYY FAIZ M", "results": [{"subject_code": "EBCC22I07", "grade": "A"}, {"subject_code": "EBCS22009", "grade": "A"}, {"subject_code": "EBCS22010", "grade": "A"}, {"subject_code": "EBCS22E11", "grade": "B"}, {"subject_code": "EBCS22L07", "grade": "H"}, {"subject_code": "EBCS22L08", "grade": "S"}, {"subject_code": "EBDS22ET6", "grade": "S"}, {"subject_code": "EBDS22I03", "grade": "S"}, {"subject_code": "EBDS22I04", "grade": "S"}, {"subject_code": "EBME22OE7", "grade": "S"}, {"subject_code": "EBCS22006", "grade": "B"}, {"subject_code": "EBCT22OE5", "grade": "A"}]},
{"student_regno": "221191101129", "student_name": "SASI KUMAR M", "results": [{"subject_code": "EBCC22I07", "grade": "A"}, {"subject_code": "EBCS22009", "grade": "A"}, {"subject_code": "EBCS22010", "grade": "A"}, {"subject_code": "EBCS22E11", "grade": "B"}, {"subject_code": "EBCS22L07", "grade": "H"}, {"subject_code": "EBCS22L08", "grade": "H"}, {"subject_code": "EBDS22ET6", "grade": "S"}, {"subject_code": "EBDS22I03", "grade": "H"}, {"subject_code": "EBDS22I04", "grade": "S"}, {"subject_code": "EBEE22OE6", "grade": "S"}]}]
filename="../static/grade-points.jsonl"
grade_points={}
with open(filename, 'r', encoding="utf-8") as in_file:
    for line in in_file:
        data=json.loads(line)
        grade_points[data['letter_grade']]=data['grade_points']

filename="../static/merged_credits.jsonl"
df = pd.read_json(filename, lines=True)
credits={}
with open(filename, 'r', encoding="utf-8") as in_file:
    for line in in_file:
        data=json.loads(line)
        credits[data['subject_code']] = data['credits']

acq_credits=0
total_credits=0

final_list=[]
current_dict={}

for line in test_dict:
        all_data= line
        if line["student_regno"] == "221191101064":
            results_data = all_data["results"]
            current_dict["student_regno"] = line["student_regno"]
            current_dict["student_name"] = line["student_name"]
            current_dict["results"] =[]
            for data in results_data:     
                try:     
                    results_dict={}
                    results_dict["subject_code"] = data['subject_code']
                    result= df.loc[df['subject_code'] == data['subject_code'], 'subject_name']
                    results_dict["subject_name"] = result.values[0]
                    results_dict["grade"] = data['grade']

                    # print(f"extracted grade : {data['grade']}, cor gp:{grade_points[data['grade']]}")
                    # print(f"scode : {data['subject_code']}, credit: {credits[data['subject_code']]}")

                    acq_credits+=grade_points[data['grade']] * credits[data['subject_code']]
                    current_ = grade_points[data['grade']] * credits[data['subject_code']]
                    # print(f"{grade_points[data['grade']]} * {credits[data['subject_code']]} = {current_}")
                    # print(f"acc : {acq_credits}")
                    total_credits+=credits[data['subject_code']]
                    # print(results_dict)
                    current_dict["results"].append(results_dict)
                    # print(current_dict["results"])
                except KeyError:
                    # print(results_data)

                    print(line["student_regno"], line["student_name"], data['subject_code'])

                    # if '0' in data['subject_code']:                 
                    #     acq_credits+=grade_points[data['grade']] * credits[data['subject_code'].replace('0','O')]
                    #     total_credits+=credits[data['subject_code'].replace('0','O')]
                    # elif 'O' in data['subject_code']:
                    #     acq_credits+=grade_points[data['grade']] * credits[data['subject_code'].replace('O','0')]
                    #     total_credits+=credits[data['subject_code'].replace('O','0')]
                    # else:
                    #     print('subject code not found.')
            # print(f"{acq_credits}/{total_credits}")
            gpa = acq_credits / total_credits
            # print(line["student_regno"], line["student_name"])
            # print(f"Gpa is {gpa:.2f}")
            current_dict["gpa"]= gpa
# print(test_dict)
print(current_dict)

