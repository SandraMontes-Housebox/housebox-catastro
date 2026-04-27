from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import xml.etree.ElementTree as ET

app = FastAPI(title="Housebox Catastro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

CATASTRO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/xml, text/xml, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://www.sedecatastro.gob.es/",
}

def get_text(root, *tags):
    for tag in tags:
        for el in root.iter():
            if el.tag.split('}')[-1] == tag and el.text:
                return el.text.strip()
    return ''

@app.get("/catastro")
async def consultar_catastro(ref: str = Query(..., min_length=14, description="Referencia catastral (14-20 caracteres)")):
    ref = ref.strip().upper().replace(' ', '')
    url = f"https://ovc.catastro.meh.es/OVCServWeb/OVCWcfLibres/OVCFotoFachada.svc/Consulta_DNPRC?RefCatastral={ref}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers=CATASTRO_HEADERS)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout consultando el Catastro")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de conexión: {str(e)}")

    if r.status_code == 403:
        raise HTTPException(status_code=403, detail="El Catastro rechazó la petición (403). Puede requerir cabeceras adicionales.")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"Catastro devolvió {r.status_code}")

    try:
        root = ET.fromstring(r.text)
        g = lambda *tags: get_text(root, *tags)

        tipo_via  = g('tv')
        nom_via   = g('nv')
        num       = g('pnp')
        planta    = g('plp')
        muni      = g('nm', 'loc')
        prov      = g('np')
        cp        = g('dp')
        uso       = g('cn', 'luso')
        sup_cons  = g('sfc', 'stl')
        sup_suelo = g('ssuelo')
        anyo      = g('ant')

        partes    = [p for p in [tipo_via, nom_via, num, planta] if p]
        direccion = ' '.join(partes) or g('ldt') or ref

        if not muni:
            return {
                "ok": False,
                "error": "Referencia no encontrada. Verifica que los 20 dígitos sean correctos.",
                "ref": ref
            }

        return {
            "ok": True,
            "ref": ref,
            "direccion": direccion,
            "municipio": muni,
            "provincia": prov,
            "cp": cp,
            "uso": uso,
            "sup_construida": sup_cons,
            "sup_suelo": sup_suelo,
            "anyo_construccion": anyo,
        }
    except ET.ParseError as e:
        raise HTTPException(status_code=500, detail=f"Error parseando XML del Catastro: {str(e)}")

@app.get("/health")
def health():
    return {"status": "ok", "service": "housebox-catastro"}
