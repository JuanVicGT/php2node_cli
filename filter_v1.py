from openpyxl import load_workbook, Workbook

src = r"D:\HomeLand\PHP Migration\EndPoints_DISCOVERED.xlsx"
dst = r"D:\HomeLand\PHP Migration\EndPoints_DISCOVERED_v1.xlsx"

wb = load_workbook(src)
ws = wb["EndPoints"]

hdr = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
ix = hdr.index("Version")

out = Workbook()
ows = out.active
ows.title = "EndPoints"
ows.append(hdr)

for row in ws.iter_rows(min_row=2, values_only=True):
    if not row or not any(row):
        continue
    v = row[ix]
    if str(v).strip().lower() == "v1":
        ows.append(list(row))

out.save(dst)
print("OK ->", dst)
