import json
import os
output_jsonls=os.listdir("./output_")
results=[]
with open("./merged_credits.jsonl", 'w', encoding='utf-8') as out_file:
    for jsonl in output_jsonls:
        with open(f"./output_/{jsonl}", "r") as in_file:
            for line in in_file:
                out_file.write(line)
                