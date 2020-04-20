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

parameters = {
    'data': [
        {
            'test': 5,
            'hello': 'working'
        }
    ],
    'general': True
}

data = {
    "jobId": 24,
    "path": "",
    "recursive": True
}

result = requests.request(
    "PATCH", "http://localhost:8000/job/apiv1/file/",
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