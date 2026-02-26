import requests

token = "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI5ODEwMDc3MSIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3MTkzNDg3NSwiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiMTg1MDI1MjM4MjciLCJvcGVuSWQiOm51bGwsInV1aWQiOiIyNDdiYTA0Ny01NDFlLTQ2YTItYTRmYi01MWVkZDE1ZDk4M2EiLCJlbWFpbCI6IiIsImV4cCI6MTc3OTcxMDg3NX0.7_d75l3AIOL9zXY91meDy15Xs8K9GBrZ1rIgpaSlrx3TzuRoKfuD2d5kjkywqhDt6NL_ZxDh1FhX4wqSYlWLXQ"
url = "https://mineru.net/api/v4/extract/task"

header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}


data = {
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "model_version": "vlm"
}

res = requests.post(url,headers=header,json=data)
print(res.status_code)
print(res.json())
print(res.json()["data"])

