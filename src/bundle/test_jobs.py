import requests
import json
import jwt
import datetime

jwt_secret = "^zzul@u)rxayk67^%3kf^59!pw&-vfv0lnv6#6h)w6!eyjzz!g"

jwt_enc = jwt.encode(
    {
        'userId': 1234,
        'exp': datetime.datetime.now() + datetime.timedelta(days=30)
    },
    jwt_secret,
    algorithm='HS256'
)

with open("params.json") as f:
    params = f.read()

data = {
    "parameters": params,
    "cluster": "localhost",
    "bundle": "fbc9f7c0815f1a83b0de36f957351c93797b2049"
}

result = requests.request(
    "POST", "http://localhost:8000/job/apiv1/job/",
    data=json.dumps(data),
    headers={
        "Authorization": jwt_enc
    }
)

print(result.status_code)
print(result.headers)
print(result.content)

# result = requests.request(
#     "GET", f"http://localhost:8000/apiv1/file/?fileId={json.loads(result.content)['fileId']}",
#     headers={
#         "Authorization": jwt_enc
#     }
# )
#
# print(result.status_code)
# print(result.headers)
# print(result.content)