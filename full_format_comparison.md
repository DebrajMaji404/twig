# Full format comparison: JSON, XML, YAML, TOON-style, Twig

Token estimate: chars/4 approximation (no real tokenizer access in this sandbox -- see script docstring).

Round-trip: JSON PASS, YAML PASS, Twig PASS (XML and TOON-style not round-trip tested -- token-size comparison only)

| N | JSON-min | JSON-pretty | XML | YAML | TOON-style | Twig |
|---|---|---|---|---|---|---|
| 1 | 156 | 226 | 197 | 153 | 138 | 136 |
| 2 | 311 | 450 | 390 | 306 | 216 | 194 |
| 5 | 778 | 1126 | 967 | 766 | 449 | 268 |
| 10 | 1555 | 2250 | 1930 | 1532 | 838 | 388 |
| 25 | 3891 | 5629 | 4821 | 3835 | 2008 | 740 |
| 50 | 7785 | 11260 | 9640 | 7672 | 3958 | 1320 |
| 100 | 15572 | 22523 | 19277 | 15348 | 7858 | 2476 |

## Reduction vs JSON (minified) at n=100

- JSON (pretty): -44.6% (larger than JSON-min)
- XML: -23.8% (larger than JSON-min)
- YAML: 1.4% (smaller than JSON-min)
- TOON-style: 49.5% (smaller than JSON-min)
- Twig: 84.1% (smaller than JSON-min)

## Sample output at n=1

### JSON (minified)
```json
[{"name": "person0", "address": {"present": {"state": "West Bengal", "district": "Paschim Bardhaman", "block": "Block-1", "landmark": "near temple", "pin": "713201"}, "permanent": {"state": "Bihar", "district": "Patna", "block": "Block-1", "landmark": "near market", "pin": "800001"}}, "experience": [{"companyName": "Tata Steel", "role": "Engineer", "years": 2, "state": "Jharkhand", "district": "East Singhbhum", "block": "Block-9", "landmark": "near river"}, {"companyName": "Infosys", "role": "Developer", "years": 3, "state": "Karnataka", "district": "Bangalore Urban", "block": "Block-1", "landmark": "near lake"}]}]
```

### XML
```xml
<records><record><name>person0</name><address><present><state>West Bengal</state><district>Paschim Bardhaman</district><block>Block-1</block><landmark>near temple</landmark><pin>713201</pin></present><permanent><state>Bihar</state><district>Patna</district><block>Block-1</block><landmark>near market</landmark><pin>800001</pin></permanent></address><experience><companyName>Tata Steel</companyName><role>Engineer</role><years>2</years><state>Jharkhand</state><district>East Singhbhum</district><block>Block-9</block><landmark>near river</landmark></experience><experience><companyName>Infosys</companyName><role>Developer</role><years>3</years><state>Karnataka</state><district>Bangalore Urban</district><block>Block-1</block><landmark>near lake</landmark></experience></record></records>
```

### YAML
```yaml
- name: person0
  address:
    present:
      state: West Bengal
      district: Paschim Bardhaman
      block: Block-1
      landmark: near temple
      pin: '713201'
    permanent:
      state: Bihar
      district: Patna
      block: Block-1
      landmark: near market
      pin: '800001'
  experience:
  - companyName: Tata Steel
    role: Engineer
    years: 2
    state: Jharkhand
    district: East Singhbhum
    block: Block-9
    landmark: near river
  - companyName: Infosys
    role: Developer
    years: 3
    state: Karnataka
    district: Bangalore Urban
    block: Block-1
    landmark: near lake
```

### TOON-style
```
name,address.present.state,address.present.district,address.present.block,address.present.landmark,address.present.pin,address.permanent.state,address.permanent.district,address.permanent.block,address.permanent.landmark,address.permanent.pin
person0,West Bengal,Paschim Bardhaman,Block-1,near temple,713201,Bihar,Patna,Block-1,near market,800001
  experience[]: companyName,role,years,state,district,block,landmark
    Tata Steel,Engineer,2,Jharkhand,East Singhbhum,Block-9,near river
    Infosys,Developer,3,Karnataka,Bangalore Urban,Block-1,near lake
```

### Twig
```
@shape:list
table:root
@tree
l1=address^-
l2=present^l1
l3=permanent^l1
@types
name
l2.state
l2.district
l2.block
l2.landmark
l2.pin
l3.state
l3.district
l3.block
l3.landmark
l3.pin
@arrays
t1=experience
@rows
person0|West Bengal|Paschim Bardhaman|Block-1|near temple|'713201|Bihar|Patna|Block-1|near market|'800001
===
table:t1
@types
_parent
_idx
companyName
role
years
state
district
block
landmark
@rows
0|0|Tata Steel|Engineer|2|Jharkhand|East Singhbhum|Block-9|near river
0|1|Infosys|Developer|3|Karnataka|Bangalore Urban|Block-1|near lake
```
