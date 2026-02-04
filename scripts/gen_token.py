import jwt
import datetime
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
payload = {
    'sub': 'developer', 
    'email': 'developer@example.com', 
    'roles': ['developer'], 
    'groups': [], 
    'workspace': None, 
    'exp': exp
}

# Encode token
token = jwt.encode(payload, 'secret123', algorithm='HS256')
with open('token.txt', 'w') as f:
    f.write(token)
print("Token written to token.txt")
