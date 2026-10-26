import os

import msal
from dotenv import load_dotenv

load_dotenv()

tenant_id = os.environ["ENTRA_TENANT_ID"]
api_client_id = os.environ["ENTRA_API_CLIENT_ID"]

authority = f"https://login.microsoftonline.com/{tenant_id}"
scope = [f"api://{api_client_id}/access_as_user"]

app = msal.PublicClientApplication(
    client_id=api_client_id,
    authority=authority,
)

flow = app.initiate_device_flow(scopes=scope)

if "user_code" not in flow:
    raise RuntimeError(
        f"Could not initiate device flow: {flow}"
    )

print(flow["message"])

result = app.acquire_token_by_device_flow(flow)

if "access_token" in result:
    print("\nAccess token acquired successfully.")
    print("Use this token locally to call your protected API.")
    print("\nACCESS TOKEN:")
    print(result["access_token"])
else:
    print("\nToken acquisition failed.")
    print("Error:", result.get("error"))
    print("Description:", result.get("error_description"))