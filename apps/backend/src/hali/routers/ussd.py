from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["ussd"])


@router.post("/ussd", response_class=PlainTextResponse)
async def ussd(sessionId: str = Form(...), serviceCode: str = Form(...), phoneNumber: str = Form(...), text: str = Form("")) -> str:
    menus = {
        "": "CON Welcome to HALI\n1. Latest alert\n2. Report hazard\n3. About HALI",
        "1": "CON Latest HALI alert: check nearby warnings before travel.\n1. Farmer actions\n2. Pastoralist actions",
        "1*1": "END Farmer actions: protect seed, clear drainage, move tools, follow local alerts.",
        "1*2": "END Pastoralist actions: move animals early, store water, avoid flood paths, share updates.",
        "2": "CON Choose hazard type\n1. Flood\n2. Drought\n3. Locust\n4. Other",
        "2*1": "END Flood report received. HALI will mark this for verification.",
        "2*2": "END Drought report received. HALI will mark this for verification.",
        "2*3": "END Locust report received. HALI will mark this for verification.",
        "2*4": "END Report received. HALI will mark this for verification.",
        "3": "END HALI turns regional warnings into local action for East African communities.",
    }
    return menus.get(text, "END Invalid choice")
