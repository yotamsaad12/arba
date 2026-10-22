"""Prints Arba's WhatsApp templates in Meta's format, or submits them for review.

python -m app.scripts.whatsapp_templates            # print the JSON
python -m app.scripts.whatsapp_templates --submit   # needs ARBA_WHATSAPP_ACCESS_TOKEN
                                                    # and ARBA_WHATSAPP_BUSINESS_ACCOUNT_ID
"""

import argparse
import json

import httpx

from app.core.config import settings
from app.whatsapp.templates import ALL


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--submit", action="store_true", help="create the templates on Meta")
    args = parser.parse_args()

    if not args.submit:
        print(json.dumps([t.meta_definition() for t in ALL], ensure_ascii=False, indent=2))
        return

    if not (settings.whatsapp_access_token and settings.whatsapp_business_account_id):
        raise SystemExit("set ARBA_WHATSAPP_ACCESS_TOKEN and ARBA_WHATSAPP_BUSINESS_ACCOUNT_ID")
    url = (
        f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
        f"{settings.whatsapp_business_account_id}/message_templates"
    )
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    for template in ALL:
        response = httpx.post(url, headers=headers, json=template.meta_definition(), timeout=30)
        print(template.name, response.status_code, response.text[:300])


if __name__ == "__main__":
    main()
