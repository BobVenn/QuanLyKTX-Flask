import pandas as pd
import random
from datetime import datetime, timedelta

# --- CẤU HÌNH ---
SO_LUONG = 20
START_ID = 5  # Bắt đầu từ SV005

# --- DỮ LIỆU MẪU TIẾNG VIỆT ---
ho_vn = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng",
         "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ"]
dem_nam = ["Văn", "Hữu", "Đức", "Thành", "Minh", "Quốc"]
dem_nu = ["Thị", "Thu", "Mai", "Ngọc", "Phương", "Khánh"]
ten_nam = ["Nam", "Hùng", "Mạnh", "Cường",
           "Tuấn", "Dũng", "Minh", "Đạt", "Sơn", "Huy"]
ten_nu = ["Lan", "Huệ", "Hoa", "Mai", "Cúc",
          "Trang", "Linh", "Nhi", "Hương", "Thảo"]
dia_chi_vn = ["Hà Nội", "Hải Phòng", "Hồ Chí Minh",
              "Đà Nẵng", "Cần Thơ", "Nam Định", "Bắc Ninh"]


def random_dob():
    # Tạo ngày sinh ngẫu nhiên từ năm 2003 đến 2005
    start_date = datetime(2003, 1, 1)
    end_date = datetime(2005, 12, 31)
    time_between_dates = end_date - start_date
    random_days = random.randrange(time_between_dates.days)
    return (start_date + timedelta(days=random_days)).strftime("%Y-%m-%d")


data = []
for i in range(SO_LUONG):
    current_id = START_ID + i
    masv = f"SV{current_id:03d}"

    gioi_tinh = random.choice(["Nam", "Nữ"])
    ho = random.choice(ho_vn)
    if gioi_tinh == "Nam":
        ten = f"{ho} {random.choice(dem_nam)} {random.choice(ten_nam)}"
    else:
        ten = f"{ho} {random.choice(dem_nu)} {random.choice(ten_nu)}"

    data.append({
        "masv": masv,
        "hoten": ten,
        "gioitinh": gioi_tinh,
        "ngaysinh": random_dob(),  # Đảm bảo có ngày sinh
        "sdt": f"09{random.randint(10000000, 99999999)}",
        "email": f"{masv.lower()}@student.ehpuni.edu.vn",
        "diachi": random.choice(dia_chi_vn)
    })

df = pd.DataFrame(data)
file_name = "ds_20_sinh_vien.xlsx"
df.to_excel(file_name, index=False)
print(f"✅ Đã tạo xong file '{file_name}'!")
