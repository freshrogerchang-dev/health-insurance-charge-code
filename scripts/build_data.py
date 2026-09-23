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
# 每個分類：(大分類, 分類名稱, 規則)；規則為代碼清單或 ("range", 起, 迄) 五碼範圍
# 大分類固定四種，供 App 做「手術 / 處置 / 檢查 / 檢驗」的頂層切換：
#   手術 = 需開刀房或侵入性切除/重建的治療性項目
#   處置 = 門診或病房內可執行的治療性技術（非傳統開刀房手術）
#   檢查 = 內視鏡、影像、尿路動力學等診斷性檢查
#   檢驗 = 抽血、驗尿等檢驗項目
# ---------------------------------------------------------------------------
GROUPS = ["手術", "處置", "檢查", "檢驗"]

CATEGORIES = [
    ("處置", "泌尿處置", [("range", "50001", "50099"),
                        "47013C", "47014C", "47087C", "49022B", "29019C",
                        "29020C", "29027C", "29028C"]),
    ("檢查", "內視鏡檢查", ["28019C", "28020C", "28021C"]),
    ("檢查", "尿路動力學", [("range", "21003", "21012"), "30510B"]),
    ("檢查", "影像/超音波", ["19001C", "19017C", "32006C",
                         ("range", "33012", "33019"), "33031B", "33052B",
                         "26019B", "26020B", "26050B", "26071B", "26021B"]),
    ("檢查", "放射介入", ["33032B", "33095B", "33099B", "33110B", "33111B",
                       "33047B", "33093B"]),
    ("檢驗", "檢驗", ["06012C", "06013C", "06009C", "06003C", "06503B",
                     "09078B", "12081C", "12198C", "27052C", "27083B",
                     "27084C", "09042C", "09121C", "27081B", "16001C",
                     "09002C", "09016C", "09003C", "09013C", "09015C",
                     "09124B"]),
    ("手術", "腎臟手術", [("range", "76001", "76099"), "N26028", "N26030",
                       "N26031", "N20009"]),
    ("手術", "腎上腺手術", ["82009B", "82010B", "82011B", "82014B"]),
    ("手術", "輸尿管手術", [("range", "77001", "77099"), "N26032", "N26033"]),
    ("手術", "膀胱手術", [("range", "78001", "78099"), "75813B", "74215B",
                       "73040B"]),
    ("手術", "尿道手術", [("range", "78201", "78299"), "80022B", "80023B",
                       "80035B"]),
    ("手術", "陰莖/陰囊手術", [("range", "78401", "78499")]),
    ("手術", "睪丸/副睪手術", [("range", "78601", "78899")]),
    ("手術", "輸精管/精索手術", [("range", "79001", "79299")]),
    ("手術", "攝護腺手術", [("range", "79401", "79499"),
                        "N20002", "N20003", "N20004", "N20005"]),
    ("手術", "小兒泌尿", ["88022B", "88028B", "88031B", "88034B", "88029C"]),
    ("手術", "鼠蹊疝氣", ["75607C", "75613C", "75614C", "75615C", "75610B",
                      "75619C", "75623C", "75624C"]),
    ("處置", "震波碎石(論病例計酬)", [("range", "97405", "97412"),
                              ("range", "97420", "97423")]),
    ("處置", "透析/移植相關", ["58002C", "58012B", "01039C", "P3411C"]),
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
    "76030B": "LNU laparoscopic nephroureterectomy 腹腔鏡腎輸尿管切除 機械手臂 達文西 robotic",
    "76031B": "LPN laparoscopic partial nephrectomy 腹腔鏡部分腎切除",
    "76032B": "laparoscopic pyelolithotomy",
    "76033B": "laparoscopic pyeloplasty UPJO",
    "76035B": "laparoscopic pyeloplasty UPJO",
    "76036B": "laparoscopic donor nephrectomy",
    "76037B": "LRN laparoscopic radical nephrectomy 腹腔鏡根除性腎切除 機械手臂 達文西 robotic",
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
    "78050B": "LRC laparoscopic radical cystectomy neobladder 機械手臂 達文西 robotic",
    "78051B": "LRC laparoscopic radical cystectomy ileal conduit 機械手臂 達文西 robotic",
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
    "79417B": "LRP laparoscopic radical prostatectomy 腹腔鏡攝護腺根除 機械手臂 達文西 robotic",
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
    "75623C": "laparoscopic inguinal hernia incarcerated 嵌頓性 腹腔鏡疝氣 機械手臂 達文西 robotic",
    "75624C": "laparoscopic inguinal hernia recurrent 復發性 腹腔鏡疝氣 機械手臂 達文西 robotic",
    # 論病例
    "97405K": "ESWL 醫學中心 單側",
    "97406A": "ESWL 區域醫院 單側",
    "97420B": "ESWL 地區醫院 單側",
    "58012B": "PD catheter Tenckhoff 腹膜透析導管",
    "58002C": "peritoneal dialysis PD",
}

# ---------------------------------------------------------------------------
# 常見申報提醒
# 大多為自行整理、非健保署逐字公告，只供提醒查核；但標示【通則五/六】的
# 幾條，是直接引用《全民健康保險醫療服務給付項目及支付標準》第二部第二章
# 第七節「手術」通則第五、六條原文（使用者提供之 115.09.01 生效版本，與
# 115 年第 4 次修正對照表核對過，該兩條規則未變動），可作為申報依據；
# 其餘仍請以當年度公告及院內審查為準。
# App 會在每項提醒前顯示醒目的「⚠ 提醒」標籤與免責聲明。
# ---------------------------------------------------------------------------
TIPS = {
    "28020C": "官方名稱僅為「診斷性輸尿管鏡檢」，未區分硬式／軟式輸尿管鏡，"
              "目前沒有獨立的軟式輸尿管鏡(RIRS)診斷代碼；臨床上多半仍以本碼"
              "申報，並於病歷/手術記錄註明「軟式輸尿管鏡／RIRS」以利區分技術"
              "別，惟不會因此變動點數。治療性軟鏡碎石請改用 77026B–77028B。"
              "【通則五】本項也未列單側／雙側，依通則五屬「對稱器官」，除另"
              "有規定外，表定點數已包含雙側費用，不得因雙側施行而加倍申報。",
    "77026B": "【通則五】品項名稱未標示單側／雙側，也沒有對應的雙側代碼。"
              "依支付標準第七節手術通則五「同一手術野內之對稱器官，除有特殊"
              "規定者外，係指二側之手術費用」，本項表定點數已包含雙側，同次"
              "雙側施行仍以本碼申報一次，不得加倍申報；通則六的「主刀 100%"
              "＋次刀 50%」是用在同次施行『不同種』手術，不適用於單純左右"
              "對稱的同一種手術。",
    "77027B": "【通則五】同 77026B：未標示單側／雙側，依通則五屬對稱器官，"
              "表定點數已包含雙側費用，雙側施行仍申報一次，不得加倍。",
    "77028B": "【通則五】同 77026B：未標示單側／雙側，依通則五屬對稱器官，"
              "表定點數已包含雙側費用，雙側施行仍申報一次，不得加倍。另可"
              "加計一般材料費及雷射光纖 91%（見上方支付規範）。",
    "77001B": "【通則五】官方名稱為「上或下三分之一輸尿管」，未標示單側／"
              "雙側；依通則五屬對稱器官，表定點數已包含雙側費用，雙側施行"
              "仍申報一次，不得加倍申報。",
    "77002B": "【通則五】官方名稱為「中三分之一輸尿管」，未標示單側／雙側；"
              "依通則五屬對稱器官，表定點數已包含雙側費用，雙側施行仍申報"
              "一次，不得加倍申報。",
    "79406B": "依「切除之攝護腺重量」分為 79406B(5–15g)／79411B(15–50g)／"
              "79412B(>50g)　三個級距，同次手術只能擇一申報，不可合併申報。",
    "79411B": "依切除攝護腺重量擇一申報，見 79406B 的提醒；請勿與 79406B、"
              "79412B 同次併報。",
    "79412B": "依切除攝護腺重量擇一申報，見 79406B 的提醒；請勿與 79406B、"
              "79411B 同次併報。",
    "79413B": "雙極 TURP/TUVP 依切除重量分為 79413B(5–15g)／79414B(15–50g)／"
              "79415B(>50g) 三個級距，同次手術只能擇一申報。",
    "79414B": "雙極 TURP/TUVP 依重量擇一申報，見 79413B 的提醒。",
    "79415B": "雙極 TURP/TUVP 依重量擇一申報，見 79413B 的提醒。",
    "50023B": "ESWL「第一次」；30 日內對同一側再次執行才能改用 50024B「第"
              "二次」，同日雙側施行時另一側才以第二次計，詳見上方支付規範。",
    "50024B": "ESWL「第二次」限 30 日內對同一側再次施行；同日雙側施行時，"
              "先做的一側以第一次(50023B)、後做的一側以第二次(本碼)計，詳見"
              "上方支付規範。",
    "76016B": "限「泌尿科專科醫師」施行（見上方支付規範），且超音波桿、"
              "取石網等費用已包含於一般材料費，不得另外加計。",
    "76031B": "含機械手臂輔助部分腎切除；比照本項申報者須於申報後二個月內"
              "上傳手術相關資訊，逾期未上傳將不予支付，詳細條件見上方支付規範。",
    "78008C": "一般材料費及單次使用電燒切除環可另加計 71%，詳見上方支付規範。",
}

# HTA (Health Technology Assessment) 評估項目：多屬技術評估或須專案審查，
# 非常態申報代碼，實際是否可用、給付方式與點數請務必洽醫院個案管理／健保
# 室或健保署最新公告，切勿逕行比照一般代碼申報。
_HTA_TIP = ("此為 HTA 評估項目（技術評估／專案性質），非常態健保給付代碼，"
            "實際給付條件、可否申報與比照方式，請務必洽醫院個案管理或健保"
            "署最新公告確認，勿逕行比照一般代碼申報。")
for _c in ("N20002", "N20003", "N20004", "N20005", "N20009",
           "N26028", "N26030", "N26031", "N26032", "N26033"):
    TIPS.setdefault(_c, _HTA_TIP)

# 機械手臂（達文西）輔助手術的醫師資格規定，在 115.09.01 生效版已從「訓練
# 時數自我認證」改為「取得相關專科學會認證」，比舊版嚴格；下列代碼的
# 支付規範已依新版更新（見 NOTE_OVERRIDES），這裡再加一條顯眼提醒。
_ROBOT_TIP = ("機械手臂輔助手術的醫師資格規定已於 115.09.01 生效版更新："
              "不再是「訓練達二十小時」即可自行認定，而是須取得「機械手臂"
              "輔助手術系統」相關專科學會核發的認證醫師資格，且核發單位要"
              "檢附認證計畫書送保險人審核通過，執行醫師名單也須報請保險人"
              "核定。請確認貴院執行醫師是否已符合新規定，詳見上方支付規範。")
for _c in ("75623C", "75624C", "76030B", "76037B", "78050B", "78051B",
           "79417B"):
    TIPS[_c] = _ROBOT_TIP + " " + TIPS.get(_c, "")

# ---------------------------------------------------------------------------
# 支付規範全文校正（使用者提供之官方 115.09.01 生效版支付標準文件校對後
# 更新，取代 TW Core IG 快照中較舊的文字；只涵蓋泌尿科「手術」章節內、
# 文字有實質差異的代碼，格式性標點差異不列入）。
# ---------------------------------------------------------------------------
NOTE_OVERRIDES = {
    "75623C": "執行「機械手臂輔助鼠蹊疝氣修補術，嵌頓性-無腸切除」，須符合"
              "下列規範：1.醫師資格：(1)具機械手臂輔助手術系統「消化外科」、"
              "「泌尿科」認證學會認證醫師資格。(2)前述核發認證單位應檢附認"
              "證計畫書(須檢附訓練課程、認證方式及認證培訓機構證明)予保險人"
              "審核通過。2.執行手術之醫師名單應報經保險人核定。3.其手術費按"
              "保險人規範之未列項申報方式辦理，比照本項申報，並於申報費用"
              "後二個月內應上傳手術相關資訊，未上傳者本項不予支付；惟因特"
              "殊情形未在規定期限內完成上傳，可檢具理由後補登錄。",
    "75624C": "執行「機械手臂輔助鼠蹊疝氣修補術，復發性-無腸切除」，須符合"
              "下列規範：1.醫師資格：(1)具機械手臂輔助手術系統「消化外科」、"
              "「泌尿科」認證學會認證醫師資格。(2)前述核發認證單位應檢附認"
              "證計畫書(須檢附訓練課程、認證方式及認證培訓機構證明)予保險人"
              "審核通過。2.執行手術之醫師名單應報經保險人核定。3.其手術費按"
              "保險人規範之未列項申報方式辦理，比照本項申報，並於申報費用"
              "後二個月內應上傳手術相關資訊，未上傳者本項不予支付；惟因特"
              "殊情形未在規定期限內完成上傳，可檢具理由後補登錄。",
    "76030B": "執行「機械手臂輔助腎臟輸尿管切除術」，須符合下列規範：1.醫"
              "師資格：(1)具機械手臂輔助手術系統「泌尿科」認證學會認證醫師"
              "資格。(2)前述核發認證單位應檢附認證計畫書(須檢附訓練課程、認"
              "證方式及認證培訓機構證明)予保險人審核通過。2.執行手術之醫師"
              "名單應報經保險人核定。3.其手術費按保險人規範之未列項申報方"
              "式辦理，比照本項申報，並於申報費用後二個月內應上傳手術相關"
              "資訊，未上傳者本項不予支付；惟因特殊情形未在規定期限內完成"
              "上傳，可檢具理由後補登錄。",
    "76031B": "1.腎半切除術heminephrectomy比照申報。2.執行「機械手臂輔助部"
              "分腎切除」，須符合下列規範：(1)醫師資格：A.具機械手臂輔助手"
              "術系統「泌尿科」認證學會認證醫師資格。B.前述核發認證單位應"
              "檢附認證計畫書(須檢附訓練課程、認證方式及認證培訓機構證明)"
              "予保險人審核通過。(2)執行手術之醫師名單應報經保險人核定。"
              "(3)適應症：A.術前影像報告為非囊狀腫瘤或囊狀惡性腫瘤。B.除上"
              "述外，術前影像報告懷疑良性腎臟腫瘤，符合下列任一條件且須事"
              "前審查：(a)符合影像學上腫瘤大於四公分或有出血疑慮。(b)單一"
              "腎臟或腎功能不全，需接受部分腎切除者。(4)其手術費按保險人"
              "規範之未列項申報方式辦理，比照本項申報，並應於申報費用後二"
              "個月內上傳手術相關資訊，未上傳者本項不予支付；惟因特殊情形"
              "未在規定期限內完成上傳，可檢具理由後補登錄。",
    "76037B": "執行「機械手臂輔助根治性腎切除術」，須符合下列規範：1.醫師"
              "資格：(1)具機械手臂輔助手術系統「泌尿科」認證學會認證醫師資"
              "格。(2)前述核發認證單位應檢附認證計畫書(須檢附訓練課程、認證"
              "方式及認證培訓機構證明)予保險人審核通過。2.執行手術之醫師名"
              "單應報經保險人核定。3.其手術費按保險人規範之未列項申報方式"
              "辦理，比照本項申報，並於申報費用後二個月內應上傳手術相關資"
              "訊，未上傳者本項不予支付；惟因特殊情形未在規定期限內完成上"
              "傳，可檢具理由後補登錄。",
    "78050B": "執行「機械手臂輔助膀胱全切除術合併骨盆腔淋巴切除術合併正位"
              "新膀胱重建」，須符合下列規範：1.醫師資格：(1)具機械手臂輔助"
              "手術系統「泌尿科」認證學會認證醫師資格。(2)前述核發認證單位"
              "應檢附認證計畫書(須檢附訓練課程、認證方式及認證培訓機構證明)"
              "予保險人審核通過。2.執行手術之醫師名單應報經保險人核定。"
              "3.其手術費按保險人規範之未列項申報方式辦理，比照本項申報，"
              "並於申報費用後二個月內應上傳手術相關資訊，未上傳者本項不予"
              "支付；惟因特殊情形未在規定期限內完成上傳，可檢具理由後補登"
              "錄。",
    "78051B": "執行「機械手臂輔助膀胱全切除術及骨盆腔淋巴切除術合併雙側輸"
              "尿管迴腸經皮分流術」，須符合下列規範：1.醫師資格：(1)具機械"
              "手臂輔助手術系統「泌尿科」認證學會認證醫師資格。(2)前述核發"
              "認證單位應檢附認證計畫書(須檢附訓練課程、認證方式及認證培訓"
              "機構證明)予保險人審核通過。2.執行手術之醫師名單應報經保險人"
              "核定。3.其手術費按保險人規範之未列項申報方式辦理，比照本項"
              "申報，並於申報費用後二個月內應上傳手術相關資訊，未上傳者本"
              "項不予支付；惟因特殊情形未在規定期限內完成上傳，可檢具理由"
              "後補登錄。",
    "79417B": "執行「機械手臂輔助根治性前列腺切除術」，須符合下列規範："
              "1.醫師資格：(1)具機械手臂輔助手術系統「泌尿科」認證學會認證"
              "醫師資格。(2)前述核發認證單位應檢附認證計畫書(須檢附訓練課"
              "程、認證方式及認證培訓機構證明)予保險人審核通過。2.執行手術"
              "之醫師名單應報經保險人核定。3.其手術費按保險人規範之未列項"
              "申報方式辦理，比照本項申報，並應於申報費用後二個月內上傳手"
              "術相關資訊，未上傳者本項不予支付；惟因特殊情形未在規定期限"
              "內完成上傳，可檢具理由後補登錄。",
}

# ---------------------------------------------------------------------------
# 手術支付點數（使用者提供之官方《全民健康保險醫療服務給付項目及支付標
# 準》115.09.01 生效版「第二部第二章第七節第十二項 泌尿及男性生殖」章節，
# 以及相關的疝氣／機械手臂條文抽取而來）。僅涵蓋「手術」大分類，「處置／
# 檢查／檢驗」尚無點數資料。N 開頭的 HTA 評估項目未列固定點數，故不在內。
# 點數如有調整，請重新提供最新支付標準文件後更新此表。
# ---------------------------------------------------------------------------
POINTS = {
    "76001B": 5946, "76002B": 16584, "76003B": 7572, "76004B": 10198,
    "76005B": 14240, "76006B": 5880, "76007B": 25780, "76008B": 7080,
    "76009C": 6828, "76010C": 6340, "76011B": 10757, "76012B": 15060,
    "76013B": 14580, "76014B": 14407, "76015B": 6440, "76016B": 13550,
    "76017B": 7332, "76018B": 39985, "76019B": 43138, "76020B": 212256,
    "76021B": 11530, "76022B": 17088, "76023B": 16980, "76024B": 6440,
    "76025B": 15179, "76026B": 18826, "76027B": 25486, "76028B": 34078,
    "76029B": 7056, "76030B": 35790, "76031B": 34176, "76032B": 10757,
    "76033B": 17885, "76034C": 8194, "76035B": 19375, "76036B": 69021,
    "76037B": 46385, "82009B": 10430, "82010B": 13609, "82011B": 14400,
    "82014B": 19623, "77001B": 7944, "77002B": 6736, "77003B": 10069,
    "77004B": 8586, "77005B": 10572, "77006B": 8496, "77007B": 10344,
    "77008B": 12020, "77009B": 12040, "77010B": 15720, "77011B": 14082,
    "77012B": 16310, "77013B": 9600, "77014B": 11333, "77015B": 10800,
    "77016B": 12960, "77017B": 17040, "77018B": 8231, "77019B": 10148,
    "77020B": 8496, "77021B": 10344, "77022B": 13675, "77023C": 2506,
    "77024B": 2904, "77026B": 5537, "77027B": 9259, "77028B": 7446,
    "77029B": 11680, "77030B": 7410, "77031B": 12877, "77032B": 12960,
    "77033B": 17040, "77034B": 7922, "77035B": 6440, "77036B": 9892,
    "77037B": 12178, "77038B": 15627, "77039B": 22459, "77040B": 26011,
    "78001C": 500, "78002C": 4956, "78003C": 3285, "78004C": 4760,
    "78005B": 4523, "78006B": 5170, "78007B": 6440, "78008C": 8027,
    "78009B": 6770, "78010C": 9670, "78011B": 13799, "78012B": 27464,
    "78013B": 21450, "78014B": 34992, "78015B": 8898, "78016B": 10800,
    "78017B": 5856, "78018B": 5470, "78019B": 11461, "78020B": 9408,
    "78021B": 13895, "78022C": 7728, "78023C": 3398, "78024C": 3568,
    "78025B": 3900, "78026C": 4675, "78027C": 5437, "78028B": 7427,
    "78029B": 9116, "78030B": 18806, "78031C": 2705, "78032C": 7760,
    "78033C": 5800, "78034B": 9912, "78035B": 13763, "78036B": 13206,
    "78037B": 9289, "78038B": 12352, "78039B": 18456, "78040B": 18479,
    "78041B": 28778, "78042B": 32647, "78043B": 19419, "78044B": 27805,
    "78045B": 35531, "78046B": 60063, "78047B": 17198, "78048B": 9274,
    "78049C": 8886, "78050B": 65785, "78051B": 65785, "75813B": 9373,
    "74215B": 17111, "73040B": 13815, "78201C": 4174, "78202B": 6814,
    "78203B": 8501, "78204B": 10285, "78205B": 13658, "78206C": 2424,
    "78207C": 3835, "78208B": 5262, "78209C": 3502, "78210C": 4062,
    "78211B": 7348, "78212B": 4334, "78213B": 13416, "78214B": 18473,
    "78215B": 6137, "78216B": 4888, "78217B": 5669, "78218B": 9638,
    "78219B": 7312, "78220B": 6197, "78221B": 3580, "78222B": 27617,
    "78223B": 27617, "78224B": 8496, "78225B": 2217, "80022B": 10899,
    "80023B": 13078, "80035B": 11680, "78401C": 2034, "78402B": 5622,
    "78403B": 8578, "78404B": 12463, "78405B": 13327, "78406B": 7393,
    "78407C": 5425, "78408C": 3623, "78409B": 4065, "78410B": 5540,
    "78411C": 3074, "78412C": 2201, "78413B": 12136, "78414B": 15412,
    "78601C": 1810, "78602C": 2904, "78603C": 5163, "78604B": 6175,
    "78605C": 7613, "78606C": 11722, "78607C": 13522, "78608C": 4581,
    "78609B": 5064, "78610B": 14576, "78611C": 4040, "78612C": 20283,
    "78801C": 5903, "78802B": 8230, "78803B": 8568, "78804B": 10802,
    "78805C": 3021, "79001C": 2693, "79002B": 8431, "79201C": 3243,
    "79202B": 4819, "79203C": 5522, "79204C": 8283, "79401C": 1841,
    "79402C": 3504, "79403B": 26050, "79404B": 9114, "79405B": 11011,
    "79406B": 11055, "79407C": 4242, "79408C": 3829, "79409C": 3156,
    "79410B": 31171, "79411B": 13210, "79412B": 15236, "79413B": 11759,
    "79414B": 13914, "79415B": 15940, "79416C": 3167, "79417B": 46756,
    "88022B": 46601, "88028B": 28371, "88031B": 18551, "88034B": 12825,
    "88029C": 14379, "75607C": 11292, "75613C": 12890, "75614C": 12565,
    "75615C": 13921, "75610B": 12422, "75619C": 19987, "75623C": 21125,
    "75624C": 22239,
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

    cat_group = {name: group for group, name, _ in CATEGORIES}
    uro, seen = [], set()
    for group, cat, rules in CATEGORIES:
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
            note = NOTE_OVERRIDES.get(code_, note)
            uro.append({"code": code_, "name": name, "cat": cat, "group": group,
                        "alias": ALIASES.get(code_, ""), "note": note,
                        "tip": TIPS.get(code_, ""),
                        "points": POINTS.get(code_)})
    missing = sorted(set(ALIASES) - seen)
    if missing:
        print("警告：以下別名代碼未被分類收錄：", missing)
    missing_tips = sorted(set(TIPS) - seen)
    if missing_tips:
        print("警告：以下提醒代碼未被分類收錄：", missing_tips)

    cats = [{"name": name, "group": group} for group, name, _ in CATEGORIES]
    dump = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))
    (ROOT / "data" / "all-codes.js").write_text(
        "// 自動產生：scripts/build_data.py\n"
        f"window.NHI_META={dump(meta)};\n"
        f"window.NHI_ALL={dump(all_rows)};\n", encoding="utf-8")
    (ROOT / "data" / "urology.js").write_text(
        "// 自動產生：scripts/build_data.py\n"
        f"window.NHI_URO={dump({'groups': GROUPS, 'categories': cats, 'synonyms': SYNONYMS, 'items': uro})};\n",
        encoding="utf-8")

    with open(ROOT / "docs" / "urology-codes.csv", "w", encoding="utf-8-sig",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["大分類", "分類", "代碼", "中文名稱", "支付點數(115.09.01)",
                    "常用別名/縮寫", "常見申報提醒(非官方)", "支付規範摘要"])
        for it in uro:
            w.writerow([it["group"], it["cat"], it["code"], it["name"],
                        it["points"] if it["points"] is not None else "",
                        it["alias"], re.sub(r"\s+", " ", it["tip"]),
                        re.sub(r"\s+", " ", it["note"])])

    n_points = sum(1 for it in uro if it["points"] is not None)
    lines = [
        "# 泌尿科常用健保處置與手術碼整理", "",
        f"- 資料來源：{meta['source']}（版本 {meta['sourceVersion']}，CC0 授權）",
        f"- 收錄：泌尿科相關 {len(uro)} 項（全部給付項目共 {len(codes)} 項，可在 App 切換「全部」查詢）",
        f"- 其中 {n_points} 項（手術大分類）已依使用者提供之《全民健康保險醫療服務"
        "給付項目及支付標準》115.09.01 生效版補上正式支付點數與最新支付規範文字；"
        "「處置／檢查／檢驗」大分類尚未有點數資料。",
        "- 支付點數與最新異動請以[健保署醫療服務給付項目查詢](https://info.nhi.gov.tw/INAE5000/INAE5001S01)為準。",
        "- 「常見申報提醒」為整理者自行歸納，**不是健保署逐字公告**，僅供提醒"
        "查核之用；標示【通則五】【通則六】的則是直接引用支付標準通則原文，"
        "可作為申報依據，其餘仍請以當年度公告及院內審查為準。",
        "- 本檔由 `scripts/build_data.py` 自動產生，請勿手動編輯。", "",
    ]
    for group in GROUPS:
        group_cats = [c["name"] for c in cats if c["group"] == group]
        group_items = [it for it in uro if it["group"] == group]
        if not group_items:
            continue
        lines += [f"# {group}（{len(group_items)}）", ""]
        for cat in group_cats:
            items = [it for it in uro if it["cat"] == cat]
            if not items:
                continue
            lines += [f"## {cat}（{len(items)}）", "",
                      "| 代碼 | 名稱 | 支付點數 | 常用別名/縮寫 | 常見申報提醒 |",
                      "|---|---|---|---|---|"]
            esc = lambda s: s.replace("|", "／")
            for it in items:
                pts = it["points"] if it["points"] is not None else "—"
                lines.append(f"| `{it['code']}` | {esc(it['name'])} | {pts} | "
                              f"{esc(it['alias'])} | {esc(it['tip'])} |")
            lines.append("")
    (ROOT / "docs" / "泌尿科健保碼整理.md").write_text("\n".join(lines),
                                                   encoding="utf-8")
    print(f"完成：全部 {len(codes)} 項，泌尿科 {len(uro)} 項，"
          f"提醒 {sum(1 for it in uro if it['tip'])} 項，點數 {n_points} 項")


if __name__ == "__main__":
    main()
