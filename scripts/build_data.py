#!/usr/bin/env python3
"""產生 App 使用的健保碼資料檔。

資料來源：衛生福利部「臺灣核心實作指引 (TW Core IG)」FHIR 套件中的
CodeSystem「臺灣健保署醫療服務給付項目」(medical-service-payment-tw)，
授權 CC0-1.0。套件發佈於 npm：tw.gov.mohw.twcore。

用法：
    python3 scripts/build_data.py            # 使用 data/ 內的來源檔，沒有則自動下載
    python3 scripts/build_data.py --download # 強制重新下載最新套件

輸出：
    data/all-codes.js        全部給付項目 (window.NHI_ALL)
    data/urology.js          泌尿科精選代碼 + 分類 + 別名 (window.NHI_URO)
    docs/urology-codes.csv   泌尿科代碼清單 (Excel 可開)
    docs/泌尿科健保碼整理.md  泌尿科代碼整理表
"""
import csv
import io
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "source-CodeSystem-medical-service-payment-tw.json"
NPM_PKG = "https://registry.npmjs.org/tw.gov.mohw.twcore"
MEMBER = "package/CodeSystem-medical-service-payment-tw.json"


def download():
    meta = json.load(urllib.request.urlopen(NPM_PKG))
    latest = meta["dist-tags"]["latest"]
    url = meta["versions"][latest]["dist"]["tarball"]
    print(f"下載 {url}")
    raw = urllib.request.urlopen(url).read()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        SRC.write_bytes(tf.extractfile(MEMBER).read())


def code_range(codes, lo, hi):
    return [c for c in codes if lo <= c[:5] <= hi]


# ---------------------------------------------------------------------------
# 泌尿科分類：依健保支付標準章節與臨床使用整理
# 每個分類：(分類名稱, 規則)；規則為代碼清單或 ("range", 起, 迄) 五碼範圍
# ---------------------------------------------------------------------------
CATEGORIES = [
    ("泌尿處置", [("range", "50001", "50099"),
                 "47013C", "47014C", "47087C", "49022B", "29019C", "29020C",
                 "29027C", "29028C"]),
    ("內視鏡檢查", ["28019C", "28020C", "28021C"]),
    ("尿路動力學", [("range", "21003", "21012"), "30510B"]),
    ("影像/超音波", ["19001C", "19017C", "32006C",
                  ("range", "33012", "33019"), "33031B", "33052B",
                  "26019B", "26020B", "26050B", "26071B", "26021B"]),
    ("放射介入", ["33032B", "33095B", "33099B", "33110B", "33111B", "33047B",
                 "33093B"]),
    ("檢驗", ["06012C", "06013C", "06009C", "06003C", "06503B", "09078B",
             "12081C", "12198C", "27052C", "27083B", "27084C", "09042C",
             "09121C", "27081B", "16001C", "09002C", "09016C", "09003C",
             "09013C", "09015C", "09124B"]),
    ("腎臟手術", [("range", "76001", "76099"), "N26028", "N26030",
                 "N26031", "N20009"]),
    ("腎上腺手術", ["82009B", "82010B", "82011B", "82014B"]),
    ("輸尿管手術", [("range", "77001", "77099"), "N26032", "N26033"]),
    ("膀胱手術", [("range", "78001", "78099"), "75813B", "74215B",
                 "73040B"]),
    ("尿道手術", [("range", "78201", "78299"), "80022B", "80023B",
                 "80035B"]),
    ("陰莖/陰囊手術", [("range", "78401", "78499")]),
    ("睪丸/副睪手術", [("range", "78601", "78899")]),
    ("輸精管/精索手術", [("range", "79001", "79299")]),
    ("攝護腺手術", [("range", "79401", "79499"),
                  "N20002", "N20003", "N20004", "N20005"]),
    ("小兒泌尿", ["88022B", "88028B", "88031B", "88034B", "88029C"]),
    ("鼠蹊疝氣", ["75607C", "75613C", "75614C", "75615C", "75610B",
               "75619C", "75623C", "75624C"]),
    ("震波碎石(論病例計酬)", [("range", "97405", "97412"),
                        ("range", "97420", "97423")]),
    ("透析/移植相關", ["58002C", "58012B", "01039C", "P3411C"]),
]

# 臨床常用英文縮寫/俗稱 → 讓關鍵字查得到
ALIASES = {
    # 處置
    "47013C": "單導 導尿 in-and-out 單次導尿 straight cath",
    "47014C": "Foley 放尿管 留置尿管 導尿管 indwelling catheter",
    "47087C": "骨盆底電刺激 pelvic floor electrical stimulation 尿失禁復健",
    "50001C": "尿道口徑 calibration",
    "50002C": "meatotomy 尿道口切開",
    "50003C": "dorsal slit 包皮背切 包莖切開",
    "50005C": "尖頭濕疣 菜花 condyloma 電燒",
    "50006C": "cystostomy care 膀胱造口 換洗",
    "50007C": "PCN care nephrostomy 腎造廔 換洗",
    "50009C": "prostate massage EPS 攝護腺按摩",
    "50010C": "retrograde ureteral catheterization RP 逆行性導管",
    "50011C": "BCG 化療灌注 intravesical instillation mitomycin epirubicin 膀胱灌藥",
    "50012C": "bladder irrigation 沖膀胱",
    "50013C": "urethral dilatation 尿道擴張 sounding",
    "50014C": "CBI continuous bladder irrigation 連續沖洗",
    "50015C": "condyloma podophyllin 菜花 藥物",
    "50017C": "scrotal abscess I&D",
    "50019C": "DJ D-J double J stent 雙J 輸尿管支架 導管置放",
    "50020C": "circumcision 割包皮 包皮環切 包皮切除",
    "50021C": "testicular torsion manual detorsion 睪丸扭轉",
    "50022C": "換管 PCN換管 cystostomy change 更換引流管 換膀胱造口管",
    "50023B": "ESWL SWL 震波碎石 體外碎石",
    "50024B": "ESWL SWL 震波碎石 第二次",
    "50027B": "VUR Deflux STING 膀胱輸尿管逆流 注射",
    "50029C": "silver nitrate 乳糜尿 chyluria",
    "50030C": "clot evacuation 血塊 血尿 清血塊",
    "50032C": "paraphimosis 包皮嵌頓 復位",
    "50033C": "hernia reduction 疝氣推回",
    "50034C": "PESA 副睪取精 取精",
    "50035B": "cryoablation 冷凍治療 腎腫瘤",
    "50036B": "Botox 肉毒 botulinum 膀胱注射 intravesical injection",
    "29019C": "suprapubic aspiration 恥骨上穿刺",
    "29020C": "hydrocele aspiration 陰囊水腫抽吸",
    "29028C": "prostate biopsy 攝護腺穿刺",
    # 內視鏡
    "28019C": "cysto cystoscopy 膀胱鏡 軟式膀胱鏡",
    "28020C": "URS diagnostic ureteroscopy 輸尿管鏡 診斷性",
    "28021C": "urethroscopy 尿道鏡",
    # 尿動力
    "21003C": "EMG 肌電圖 sphincter",
    "21004C": "uroflowmetry UFR uroflow 尿流速 解尿速度",
    "21005C": "UPP urethral pressure profile",
    "21006B": "VUDS video urodynamics 錄影尿動力",
    "21007C": "CMG cystometry 膀胱壓",
    "21008C": "bladder scan 膀胱掃描 殘尿",
    "21009B": "urecholine test",
    "21010C": "PVR post-void residual 殘尿 餘尿 膀胱超音波",
    "21011C": "pressure flow study PFS 壓力流速 urodynamic UDS 尿動力學",
    "21012B": "stress UPP 應力性尿失禁",
    # 影像
    "19001C": "abdominal echo sono 腹部超音波 腎臟超音波 renal echo",
    "19017C": "TRUS transrectal ultrasound 經直腸超音波 攝護腺超音波",
    "32006C": "KUB 腹部X光",
    "33012B": "IVP IVU intravenous pyelography 靜脈腎盂攝影",
    "33013B": "RP retrograde pyelography 逆行性腎盂攝影",
    "33014B": "RP retrograde pyelography 逆行性腎盂攝影 雙側",
    "33015B": "cystography 膀胱攝影",
    "33016B": "VCUG voiding cystourethrography 排尿膀胱尿道攝影",
    "33017B": "chain cystography",
    "33019B": "antegrade pyelography 順行性",
    "33031B": "RUG retrograde urethrography 尿道攝影",
    "33052B": "vasography 輸精管攝影",
    "26020B": "renal scan DMSA 腎掃描",
    "26050B": "renogram DTPA MAG3 腎功能掃描 利尿腎圖",
    "26071B": "diuretic renogram lasix renogram",
    "26019B": "scrotal scan",
    # 放射介入
    "33032B": "PCN percutaneous nephrostomy 經皮腎造廔",
    "33095B": "PCN change 換PCN 腎造廔管更換",
    "33099B": "antegrade DJ 經皮DJ 順行性支架",
    # 檢驗
    "06012C": "UA U/A urinalysis 尿液常規 尿檢",
    "06013C": "urine dipstick 尿生化",
    "06009C": "urine sediment 尿沉渣",
    "09078B": "stone analysis 結石成分",
    "12081C": "PSA 攝護腺特異抗原",
    "12198C": "free PSA fPSA 游離PSA",
    "27052C": "PSA RIA",
    "27083B": "free PSA RIA",
    "27084C": "p2PSA PHI",
    "09121C": "testosterone 睪固酮 男性荷爾蒙",
    "27081B": "testosterone 睪固酮",
    "16001C": "semen analysis 精液檢查 精蟲",
    "09002C": "BUN",
    "09015C": "creatinine Cr 肌酸酐",
    "09016C": "urine creatinine",
    "09013C": "uric acid 尿酸",
    # 腎
    "76002B": "pyelotomy",
    "76003B": "renal biopsy open",
    "76004B": "simple nephrectomy 腎切除",
    "76005B": "PN partial nephrectomy 部分腎切除",
    "76006B": "renal cyst excision 腎囊腫",
    "76007B": "radical nephrectomy LND 淋巴",
    "76010C": "open nephrostomy",
    "76011B": "nephrolithotomy pyelolithotomy 腎結石 開刀取石",
    "76012B": "staghorn 鹿角結石 anatrophic",
    "76014B": "pyeloplasty UPJO 腎盂輸尿管交界狹窄",
    "76016B": "PCNL PNL percutaneous nephrolithotomy 經皮腎取石 腎結石",
    "76017B": "nephroscopy PCN nephroscope",
    "76019B": "living donor nephrectomy 活體捐腎",
    "76020B": "kidney transplant renal transplantation KT 換腎",
    "76021B": "LN laparoscopic nephrectomy 腹腔鏡腎切除",
    "76022B": "AML angiomyolipoma",
    "76024B": "endopyelotomy",
    "76025B": "NU nephroureterectomy 腎輸尿管切除",
    "76026B": "NU nephroureterectomy bladder cuff UTUC 上泌尿道上皮癌",
    "76027B": "RN radical nephrectomy 根除性腎切除 RCC 腎細胞癌",
    "76028B": "IVC thrombectomy tumor thrombus",
    "76029B": "renal cyst unroofing decortication 腎囊腫 腹腔鏡",
    "76030B": "LNU laparoscopic nephroureterectomy 腹腔鏡腎輸尿管切除",
    "76031B": "LPN laparoscopic partial nephrectomy 腹腔鏡部分腎切除",
    "76032B": "laparoscopic pyelolithotomy",
    "76033B": "laparoscopic pyeloplasty UPJO",
    "76035B": "laparoscopic pyeloplasty UPJO",
    "76036B": "laparoscopic donor nephrectomy",
    "76037B": "LRN laparoscopic radical nephrectomy 腹腔鏡根除性腎切除",
    "N26030": "RAPN robotic partial nephrectomy 機械手臂 達文西",
    "N26031": "robotic nephrectomy 機械手臂 達文西",
    "N26028": "robotic kidney transplant 機械手臂",
    "N20009": "renal denervation RDN 高血壓",
    # 腎上腺
    "82009B": "adrenalectomy",
    "82014B": "LA laparoscopic adrenalectomy 腹腔鏡腎上腺",
    # 輸尿管
    "77001B": "ureterolithotomy 輸尿管取石 開刀",
    "77002B": "ureterolithotomy 輸尿管取石 開刀",
    "77003B": "distal ureterectomy bladder cuff",
    "77008B": "ureteropyelostomy",
    "77009B": "ureteroureterostomy UU",
    "77010B": "transureteroureterostomy TUU",
    "77011B": "ureteral reimplantation UNC ureteroneocystostomy 輸尿管再植",
    "77012B": "ureteral reimplantation bilateral 雙側",
    "77018B": "cutaneous ureterostomy",
    "77022B": "ileal conduit Bricker 迴腸導管",
    "77023C": "ureteral catheterization",
    "77024B": "ureteral dilatation balloon 氣球擴張 狹窄",
    "77026B": "URS URSL ureteroscopic lithotripsy 輸尿管鏡碎石 pneumatic 氣動",
    "77027B": "URS URSL ultrasonic EHL 輸尿管鏡碎石",
    "77028B": "URS URSL laser lithotripsy holmium 雷射碎石 RIRS 軟式輸尿管鏡",
    "77030B": "LUL laparoscopic ureterolithotomy 腹腔鏡輸尿管取石",
    "77032B": "ileal conduit",
    "77033B": "ileal conduit bilateral",
    "77034B": "endoureterotomy",
    "77039B": "laparoscopic ureteral reimplantation",
    "77040B": "laparoscopic ureteral reimplantation bilateral",
    "N26032": "robotic ureteral reimplantation 機械手臂",
    "N26033": "robotic ureterolithotomy 機械手臂",
    # 膀胱
    "78001C": "bladder aspiration suprapubic",
    "78002C": "cystostomy suprapubic cystostomy 恥骨上膀胱造口",
    "78003C": "cystostomy suprapubic cystostomy 恥骨上膀胱造口",
    "78005B": "cystolithotomy 膀胱結石 開刀",
    "78008C": "TURBT TUR-BT TURBt 膀胱腫瘤 電切 bladder tumor",
    "78009B": "open bladder tumor excision",
    "78010C": "partial cystectomy",
    "78011B": "radical cystectomy RC",
    "78012B": "radical cystectomy neobladder 新膀胱",
    "78013B": "radical cystectomy PLND",
    "78014B": "radical cystectomy PLND neobladder",
    "78015B": "cystoplasty",
    "78018B": "cystorrhaphy",
    "78019B": "VVF vesicovaginal fistula",
    "78023C": "ureteral meatotomy ureterocele",
    "78024C": "cystoscopic ureteral stone removal",
    "78025B": "TUIBN BNI bladder neck incision 膀胱頸切開",
    "78026C": "cystolitholapaxy 膀胱碎石 膀胱結石",
    "78027C": "cystolitholapaxy 膀胱碎石 膀胱結石 大結石",
    "78028B": "incontinence surgery SUI 尿失禁",
    "78029B": "Kelly plication SUI 尿失禁",
    "78030B": "Burch colposuspension SUI 尿失禁",
    "78031C": "hydrodistension IC BPS 間質性膀胱炎 水擴張",
    "78034B": "bladder rupture repair 膀胱破裂",
    "78035B": "augmentation cystoplasty enterocystoplasty 膀胱擴大",
    "78036B": "bladder suspension sling SUI 尿失禁",
    "78037B": "Kelly SUI 尿失禁",
    "78038B": "AUS artificial urinary sphincter 人工括約肌",
    "78039B": "radical cystoprostatectomy RCP",
    "78041B": "RCP neobladder",
    "78043B": "RCP PLND",
    "78045B": "RCP PLND neobladder",
    "78047B": "laparoscopic bladder neck suspension",
    "78049C": "TURBT URS 膀胱腫瘤 電切 輸尿管鏡",
    "78050B": "LRC laparoscopic radical cystectomy neobladder",
    "78051B": "LRC laparoscopic radical cystectomy ileal conduit",
    "75813B": "urachal remnant 臍尿管",
    "73040B": "ileal conduit revision stoma",
    # 尿道
    "78201C": "urethral stone 尿道結石",
    "78202B": "urethroplasty stricture 尿道狹窄 anterior",
    "78203B": "urethroplasty stricture 尿道狹窄 posterior",
    "78206C": "urethral caruncle polyp 尿道肉阜",
    "78207C": "urethrostomy perineal",
    "78208B": "urethral diverticulum",
    "78209C": "internal urethrotomy Otis 尿道狹窄",
    "78210C": "DVIU direct vision internal urethrotomy 尿道狹窄 切開",
    "78213B": "hypospadias 尿道下裂",
    "78214B": "hypospadias 尿道下裂",
    "78215B": "TUIP transurethral incision of prostate 攝護腺切開",
    "78219B": "penile fracture 陰莖骨折",
    "78221B": "penile fracture 陰莖骨折",
    "78222B": "hypospadias chordee 尿道下裂",
    "78223B": "hypospadias 尿道下裂",
    "78224B": "urethrectomy",
    "80022B": "urethrovaginal fistula",
    "80023B": "VVF vesicovaginal fistula",
    "80035B": "sling TVT TOT midurethral sling 尿失禁 吊帶",
    # 陰莖/陰囊
    "78401C": "penile biopsy",
    "78402B": "partial penectomy 陰莖癌",
    "78403B": "total penectomy",
    "78407C": "hydrocelectomy 陰囊水腫 hydrocele",
    "78409B": "scrotectomy",
    "78410B": "Nesbit Peyronie 陰莖彎曲 plication",
    "78412C": "scrotal abscess I&D",
    # 睪丸
    "78601C": "testicular biopsy TESE 取精",
    "78602C": "testicular biopsy TESE 取精 雙側",
    "78603C": "orchiectomy 睪丸切除 去勢",
    "78604B": "bilateral orchiectomy castration 去勢 攝護腺癌",
    "78605C": "orchiopexy 睪丸固定 torsion",
    "78606C": "orchiopexy bilateral",
    "78607C": "orchiopexy cryptorchidism 隱睪 UDT",
    "78609B": "radical orchiectomy inguinal 睪丸癌",
    "78610B": "radical orchiectomy RPLND",
    "78611C": "laparoscopic orchiectomy",
    "78612C": "orchiopexy cryptorchidism 隱睪 雙側",
    "78801C": "epididymectomy",
    "78803B": "vasoepididymostomy VE",
    "78805C": "epididymal abscess",
    # 輸精管/精索
    "79001C": "vasectomy 結紮 男性結紮 輸精管結紮",
    "79202B": "varicocelectomy 精索靜脈曲張",
    "79203C": "varicocelectomy high ligation Palomo 精索靜脈曲張",
    "79204C": "laparoscopic varicocelectomy 精索靜脈曲張",
    # 攝護腺
    "79401C": "prostate biopsy needle 攝護腺切片",
    "79403B": "RP radical prostatectomy 攝護腺癌",
    "79404B": "suprapubic prostatectomy open prostatectomy",
    "79405B": "retropubic prostatectomy",
    "79406B": "TURP 攝護腺刮除 電刮 BPH 攝護腺肥大",
    "79407C": "TUR biopsy",
    "79408C": "prostatic abscess",
    "79410B": "RP PLND radical prostatectomy",
    "79411B": "TURP 攝護腺刮除 電刮 BPH 攝護腺肥大",
    "79412B": "TURP 攝護腺刮除 電刮 BPH 攝護腺肥大",
    "79413B": "bipolar TURP TUVP B-TURP PKRP 雙極 汽化 BPH",
    "79414B": "bipolar TURP TUVP B-TURP PKRP 雙極 汽化 BPH",
    "79415B": "bipolar TURP TUVP B-TURP PKRP 雙極 汽化 BPH",
    "79416C": "TRUS biopsy prostate biopsy 攝護腺切片 超音波導引",
    "79417B": "LRP laparoscopic radical prostatectomy 腹腔鏡攝護腺根除",
    "N20002": "PVP GreenLight 綠光 雷射 BPH",
    "N20003": "ThuLEP ThuVARP thulium 銩雷射 BPH",
    "N20004": "HoLEP holmium 鈥雷射 BPH",
    "N20005": "DiLEP diode laser 二極體雷射 BPH",
    # 小兒 / 疝氣
    "88022B": "bladder exstrophy",
    "88028B": "hypospadias island flap 尿道下裂",
    "88029C": "pediatric inguinal hernia herniotomy 小兒疝氣",
    "75607C": "inguinal hernia herniorrhaphy 疝氣 mesh",
    "75610B": "laparoscopic hernia TEP TAPP",
    "75619C": "laparoscopic inguinal hernia TEP TAPP 腹腔鏡疝氣",
    # 論病例
    "97405K": "ESWL 醫學中心 單側",
    "97406A": "ESWL 區域醫院 單側",
    "97420B": "ESWL 地區醫院 單側",
    "58012B": "PD catheter Tenckhoff 腹膜透析導管",
    "58002C": "peritoneal dialysis PD",
}

# 常見別名群組（這些字彼此視為同義，搜尋其一也會找到另一個）
SYNONYMS = [
    ["攝護腺", "前列腺", "prostate"],
    ["睪", "睾"],
    ["廔", "瘻"],
    ["海棉體", "海綿體"],
    ["部份", "部分"],
    ["取石", "除石"],
    ["震波", "電震波", "eswl"],
    ["腹腔鏡", "laparoscopic", "lap"],
    ["切片", "biopsy", "bx"],
    ["達文西", "機械手臂", "robot", "robotic"],
    ["結石", "stone"],
]


def main():
    if "--download" in sys.argv or not SRC.exists():
        download()
    cs = json.loads(SRC.read_text(encoding="utf-8"))
    concepts = {c["code"]: c for c in cs["concept"]}
    codes = sorted(concepts)
    meta = {
        "source": "衛生福利部 TW Core IG — 臺灣健保署醫療服務給付項目 CodeSystem",
        "sourceVersion": cs.get("version", ""),
        "count": len(codes),
    }

    def row(code):
        c = concepts[code]
        eff = next((p.get("valueDateTime") for p in c.get("property", [])
                    if p["code"] == "effectiveDate"), "")
        return [code, c.get("display", ""), c.get("definition", ""), eff]

    all_rows = [row(c) for c in codes]

    uro, seen = [], set()
    for cat, rules in CATEGORIES:
        picked = []
        for r in rules:
            if isinstance(r, tuple):
                picked += code_range(codes, r[1], r[2])
            elif r in concepts:
                picked.append(r)
            else:
                print(f"警告：{r} 不在資料中，略過")
        for code in picked:
            if code in seen:
                continue
            seen.add(code)
            code_, name, note, eff = row(code)
            uro.append({"code": code_, "name": name, "cat": cat,
                        "alias": ALIASES.get(code_, ""), "note": note})
    missing = sorted(set(ALIASES) - seen)
    if missing:
        print("警告：以下別名代碼未被分類收錄：", missing)

    cats = [c for c, _ in CATEGORIES]
    dump = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))
    (ROOT / "data" / "all-codes.js").write_text(
        "// 自動產生：scripts/build_data.py\n"
        f"window.NHI_META={dump(meta)};\n"
        f"window.NHI_ALL={dump(all_rows)};\n", encoding="utf-8")
    (ROOT / "data" / "urology.js").write_text(
        "// 自動產生：scripts/build_data.py\n"
        f"window.NHI_URO={dump({'categories': cats, 'synonyms': SYNONYMS, 'items': uro})};\n",
        encoding="utf-8")

    with open(ROOT / "docs" / "urology-codes.csv", "w", encoding="utf-8-sig",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["分類", "代碼", "中文名稱", "常用別名/縮寫", "支付規範摘要"])
        for it in uro:
            w.writerow([it["cat"], it["code"], it["name"], it["alias"],
                        re.sub(r"\s+", " ", it["note"])])

    lines = [
        "# 泌尿科常用健保處置與手術碼整理", "",
        f"- 資料來源：{meta['source']}（版本 {meta['sourceVersion']}，CC0 授權）",
        f"- 收錄：泌尿科相關 {len(uro)} 項（全部給付項目共 {len(codes)} 項，可在 App 切換「全部」查詢）",
        "- 支付點數與最新異動請以[健保署醫療服務給付項目查詢](https://info.nhi.gov.tw/INAE5000/INAE5001S01)為準。",
        "- 本檔由 `scripts/build_data.py` 自動產生，請勿手動編輯。", "",
    ]
    for cat in cats:
        items = [it for it in uro if it["cat"] == cat]
        if not items:
            continue
        lines += [f"## {cat}（{len(items)}）", "",
                  "| 代碼 | 名稱 | 常用別名/縮寫 |", "|---|---|---|"]
        for it in items:
            esc = lambda s: s.replace("|", "／")
            lines.append(f"| `{it['code']}` | {esc(it['name'])} | {esc(it['alias'])} |")
        lines.append("")
    (ROOT / "docs" / "泌尿科健保碼整理.md").write_text("\n".join(lines),
                                                   encoding="utf-8")
    print(f"完成：全部 {len(codes)} 項，泌尿科 {len(uro)} 項")


if __name__ == "__main__":
    main()
