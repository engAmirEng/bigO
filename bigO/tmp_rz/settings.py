import environ

env = environ.Env()

bucket = env.str("rz_bucket")
org = env.str("rz_org")
token = env.str("rz_token")
url = env.str("rz_url")
