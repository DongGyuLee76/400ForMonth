import sqlite3
import re

DB_NAME = "financial_plan.db"

data = """
연도(세)	연금저축/IRP	ISA 계좌	일반계좌	합계(잔액)	예상건보료	예상세금	주요 인출 및 운용 전략
2026(50)	7900	1100	20,000	29,000	근로 중	세액공제	시작: 연금 7,000 / ISA 0 / 일반 20,000
2027(51)	9195	2255	22,800	34,250	근로 중	세액공제	일반계좌 14% 수익률 복리 가동
2028(52)	10555	3468	25,992	40,015	근로 중	세액공제	대전 주택 매도 및 부채 상환 완료
2029(53)	11983	4741	29,631	46,355	근로 중	세액공제	일반계좌 배당 1,000만 원 미만 관리
2030(54)	13482	6078	33,779	53,339	근로 중	세액공제	-
2031(55)	15056	7482	38,508	61,046	근로 중	세액공제	연금 수령 자격 확보 시점
2032(56)	16709	8956	43,899	69,564	근로 중	세액공제	-
2033(57)	18444	10504	50,045	78,993	근로 중	세액공제	-
2034(58)	20266	12129	57,051	89,446	근로 중	세액공제	-
2035(59)	22180	13836	65,038	101,054	근로 중	세액공제	은퇴 전 최종 포트폴리오 점검
2036(60)	28000	30000	43,054	101,054	임의계속	0	[리밸런싱] 일반 → ISA 전환(건보료 대비)
2037(61)	26400	26700	49,082	102,182	임의계속	82.5	인출: 연금 1,500 + ISA 3,300
2038(62)	24720	23235	55,953	103,908	임의계속	82.5	인출: 연금 1,500 + ISA 3,300
2039(63)	22956	19597	63,786	106,339	약 320	82.5	지역가입 전환. 동일 인출 유지
2040(64)	21104	15777	72,716	109,597	약 310	82.5	-
2041(65)	19159	15486	82,896	117,541	약 430	230	국민연금 개시. 연금 1,500 + ISA 1,080
2042(66)	17117	15180	94,501	126,798	약 420	230	-
2043(67)	14973	14859	107,731	137,563	약 420	230	-
2044(68)	12722	14522	122,813	150,057	약 410	230	-
2045(69)	10358	14128	140,007	164,493	약 510	310	부인 국민연금 합산. 건보료 최대 구간
2046(70)	8626	13814	159,608	182,048	510	310	국민연금 3,180 + 연금 1,500 + ISA 120
2047(71)	7557	14505	181,953	204,015	510	310	-
2048(72)	6435	15230	207,426	229,091	510	310	-
2049(73)	5257	15991	236,466	257,714	510	310	-
2050(74)	4020	16791	269,571	290,382	510	310	-
2051(75)	2721	17631	307,311	327,663	500	310	-
2052(76)	1357	18512	350,335	370,204	500	310	-
2053(77)	0	18118	399,382	417,500	500	310	연금저축 소진. ISA 인출 비중 확대
2054(78)	0	17404	455,295	472,699	490	310	-
2055(79)	0	0	519,036	519,036	650	500	ISA 소진. 일반계좌 인출 개시
2056(80)	0	0	591,701	591,701	660	520	-
2057(81)	0	0	674,539	674,539	680	550	-
2058(82)	0	0	768,974	768,974	700	580	-
2059(83)	0	0	876,630	876,630	720	610	자산 8억 돌파
2060(84)	0	0	999,358	999,358	750	640	-
2061(85)	0	0	1,139,268	1,139,268	770	670	-
2062(86)	0	0	1,298,766	1,298,766	790	700	-
2063(87)	0	0	1,480,593	1,480,593	810	720	-
2064(88)	0	0	1,687,876	1,687,876	820	730	-
2065(89)	0	0	1,924,179	1,924,179	820	740	-
2066(90)	0	0	2,193,564	2,193,564	820	750	최종 21.9억 상속 자산 달성
"""

def clean_money(val):
    if not val:
        return 0
    # Remove commas and convert to int
    val = val.replace(',', '')
    try:
        return int(val)
    except ValueError:
        return 0

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Create table if not exists (in case app.py hasn't run yet)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS plan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year INTEGER NOT NULL UNIQUE,
        age INTEGER NOT NULL,
        pension_savings INTEGER DEFAULT 0,
        isa_account INTEGER DEFAULT 0,
        general_account INTEGER DEFAULT 0,
        total INTEGER DEFAULT 0,
        health_insurance TEXT,
        tax TEXT,
        withdrawal_strategy TEXT
    )
''')

# Parse and insert data
lines = data.strip().split('\n')
for line in lines:
    if not line.strip(): continue
    
    # Try tab split first
    parts = line.strip().split('\t')
    if len(parts) < 3:
         # formatted with multiple spaces?
         parts = re.split(r'\s{2,}', line.strip())

    if len(parts) < 2: continue

    # Map parts to columns
    # 0: Year(Age)
    # 1: Pension
    # 2: ISA
    # 3: General
    # 4: Total
    # 5: Health
    # 6: Tax
    # 7: Strategy
    
    # Ensure minimum length
    while len(parts) < 8:
        parts.append('')

    year_age = parts[0]
    
    # Parse Year(Age) like 2026(50)
    match = re.match(r'(\d+)\((\d+)\)', year_age)
    if not match:
        continue
        
    year = int(match.group(1))
    age = int(match.group(2))

    pension_val = clean_money(parts[1])
    isa_val = clean_money(parts[2])
    general_val = clean_money(parts[3])
    total_val = clean_money(parts[4])
    
    health = parts[5]
    tax = parts[6]
    strategy = parts[7]

    try:
        cursor.execute('''
            INSERT OR REPLACE INTO plan (year, age, pension_savings, isa_account, general_account, total, health_insurance, tax, withdrawal_strategy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (year, age, pension_val, isa_val, general_val, total_val, health, tax, strategy))
    except Exception as e:
        print(f"Error inserting {year}: {e}")

conn.commit()
conn.close()
print("Database seeded successfully.")
