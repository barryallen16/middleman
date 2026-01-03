import pandas as pd
df=pd.read_csv("tt.csv")
dict=df.to_dict
print(dict)