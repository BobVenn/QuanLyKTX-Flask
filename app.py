from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import pyodbc
import io
import base64
import datetime
import pandas as pd
import qrcode
import matplotlib
import matplotlib.pyplot as plt

# Chế độ không GUI để chạy web mượt hơn
matplotlib.use('Agg')

app = Flask(__name__)
app.secret_key = 'ktx_super_secret_key_2025'

# =================================================================
#  CẤU HÌNH KẾT NỐI DATABASE
# =================================================================


def get_db():
    try:
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=DESKTOP-3G92M40\\SQLEXPRESS;'  # Sửa lại server của bạn nếu cần
            'DATABASE=QuanLyKyTucXa;'
            'Trusted_Connection=yes;'
        )
        return conn
    except Exception as e:
        print(f"Lỗi kết nối DB: {e}")
        return None


def login_required(role=None):
    if 'user_id' not in session:
        return False
    if role and session.get('role') != role:
        return False
    return True

# =================================================================
#  1. AUTHENTICATION (Đăng nhập/Đăng xuất)
# =================================================================


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT UserID, Role FROM Users WHERE Username=? AND Password=?", (user, pwd))
        acc = cursor.fetchone()
        conn.close()

        if acc:
            session['user_id'] = acc[0]
            session['role'] = acc[1].strip()
            session['username'] = user

            # Nếu là sinh viên, lấy luôn MaSV lưu vào session
            if session['role'] == 'sinhvien':
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT MaSV FROM SinhVien WHERE UserID=?", (acc[0],))
                sv = cursor.fetchone()
                conn.close()
                if sv:
                    session['masv'] = sv[0]
                return redirect(url_for('student_home'))

            return redirect(url_for('admin_dashboard'))
        else:
            flash('Sai tài khoản hoặc mật khẩu!', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        old_pass = request.form['old_pass']
        new_pass = request.form['new_pass']
        confirm_pass = request.form['confirm_pass']

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT Password FROM Users WHERE UserID=?",
                       (session['user_id'],))
        current_db_pass = cursor.fetchone()[0]

        if current_db_pass != old_pass:
            flash('Mật khẩu hiện tại không đúng!', 'danger')
        elif new_pass != confirm_pass:
            flash('Mật khẩu mới không khớp!', 'danger')
        elif len(new_pass) < 6:
            flash('Mật khẩu mới phải có ít nhất 6 ký tự!', 'warning')
        else:
            cursor.execute(
                "UPDATE Users SET Password=? WHERE UserID=?", (new_pass, session['user_id']))
            conn.commit()
            flash('Đổi mật khẩu thành công! Vui lòng đăng nhập lại.', 'success')
            conn.close()
            return redirect(url_for('logout'))

        conn.close()
    return render_template('change_password.html')

# =================================================================
#  2. ADMIN: DASHBOARD & THỐNG KÊ
# =================================================================


@app.route('/admin/dashboard')
def admin_dashboard():
    if not login_required('admin'):
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    # Số liệu thống kê
    stats = {}
    cursor.execute("SELECT COUNT(*) FROM SinhVien")
    stats['sv'] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM Phong WHERE TrangThai=N'Trống'")
    stats['phong'] = cursor.fetchone()[0]
    cursor.execute(
        "SELECT ISNULL(SUM(SoTien), 0) FROM HoaDon WHERE TrangThai=N'Đã thanh toán'")
    stats['thu'] = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM HoaDon WHERE TrangThai=N'Chưa thanh toán'")
    stats['no'] = cursor.fetchone()[0]

    # Biểu đồ
    cursor.execute("""
        SELECT TOP 6 CONCAT(MONTH(NgayLap), '/', YEAR(NgayLap)), SUM(SoTien)
        FROM HoaDon WHERE TrangThai = N'Đã thanh toán'
        GROUP BY YEAR(NgayLap), MONTH(NgayLap)
        ORDER BY YEAR(NgayLap) DESC, MONTH(NgayLap) DESC
    """)
    data = cursor.fetchall()
    conn.close()

    months = [row[0] for row in reversed(data)]
    revenues = [row[1] for row in reversed(data)]

    img = io.BytesIO()
    if months:
        plt.figure(figsize=(10, 4))
        plt.bar(months, revenues, color='#1abc9c')
        plt.title('Doanh Thu Thực Tế (VNĐ)')
        plt.grid(axis='y', alpha=0.3)
        plt.savefig(img, format='png', bbox_inches='tight')
        plt.close()
        img.seek(0)
        plot_url = base64.b64encode(img.getvalue()).decode()
    else:
        plot_url = None

    now_str = datetime.datetime.now().strftime("%d/%m/%Y")
    return render_template('dashboard.html', stats=stats, plot_url=plot_url, now=now_str)

# =================================================================
# =================================================================
#  3. ADMIN: QUẢN LÝ PHÒNG (CODE CHUẨN - DÙNG CÁI NÀY)
# =================================================================


@app.route('/admin/phong', methods=['GET', 'POST'])
def admin_phong():
    if not login_required('admin'):
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    # --- XỬ LÝ POST ---
    if request.method == 'POST':
        act = request.form.get('action')

        # 1. THÊM PHÒNG
        if act == 'add_room':
            mp = request.form.get('maphong').strip().upper()
            cursor.execute("SELECT Count(*) FROM Phong WHERE MaPhong=?", (mp,))
            if cursor.fetchone()[0] > 0:
                flash(f'Mã phòng {mp} đã tồn tại!', 'danger')
            else:
                cursor.execute("INSERT INTO Phong (MaPhong, Toa, Khu, SucChua, TrangThai) VALUES (?, ?, ?, ?, N'Trống')",
                               (mp, request.form.get('toa'), request.form.get('khu'), request.form.get('succhua')))
                conn.commit()
                flash(f'Đã thêm phòng {mp}!', 'success')

        # 2. XẾP CHỖ (QUAN TRỌNG: Logic đếm trực tiếp để sửa lỗi)
        elif act == 'add_student_to_room':
            masv = request.form.get('masv').strip().upper()
            phong = request.form.get('phong_id')

            cursor.execute(
                "SELECT Count(*) FROM SinhVien WHERE MaSV=?", (masv,))
            if cursor.fetchone()[0] == 0:
                flash('Mã sinh viên không tồn tại!', 'danger')
            else:
                # Đếm số người thực tế đang ở trong phòng
                cursor.execute("""
                    SELECT SucChua, (SELECT COUNT(*) FROM SinhVien WHERE Phong=?) 
                    FROM Phong WHERE MaPhong=?
                """, (phong, phong))
                room_info = cursor.fetchone()

                suc_chua = int(room_info[0])
                da_o = int(room_info[1])

                if da_o >= suc_chua:
                    flash(
                        f'⛔ Phòng {phong} đã đầy ({da_o}/{suc_chua})!', 'danger')
                else:
                    cursor.execute(
                        "UPDATE SinhVien SET Phong=?, NgayVao=GETDATE() WHERE MaSV=?", (phong, masv))

                    # Cập nhật trạng thái hiển thị
                    new_status = 'Đầy' if (da_o + 1) >= suc_chua else 'Trống'
                    cursor.execute(
                        "UPDATE Phong SET TrangThai=? WHERE MaPhong=?", (new_status, phong))

                    conn.commit()
                    flash(f'✅ Đã xếp {masv} vào phòng {phong}!', 'success')

        # 3. XÓA SV KHỎI PHÒNG
        elif act == 'remove_student':
            masv = request.form.get('masv')
            # Lấy phòng cũ để update trạng thái
            cursor.execute("SELECT Phong FROM SinhVien WHERE MaSV=?", (masv,))
            old_room = cursor.fetchone()

            cursor.execute(
                "UPDATE SinhVien SET Phong=NULL, NgayVao=NULL WHERE MaSV=?", (masv,))

            if old_room and old_room[0]:
                cursor.execute(
                    "UPDATE Phong SET TrangThai=N'Trống' WHERE MaPhong=?", (old_room[0],))

            conn.commit()
            flash(f'Đã đưa {masv} ra khỏi phòng!', 'warning')

        # 4. XÓA PHÒNG
        elif act == 'delete_room':
            mp = request.form.get('maphong')
            cursor.execute(
                "SELECT Count(*) FROM SinhVien WHERE Phong=?", (mp,))
            if cursor.fetchone()[0] > 0:
                flash('Không thể xóa phòng đang có người ở!', 'danger')
            else:
                cursor.execute("DELETE FROM Phong WHERE MaPhong=?", (mp,))
                conn.commit()
                flash('Đã xóa phòng thành công!', 'success')

        return redirect(url_for('admin_phong'))

    # --- XỬ LÝ GET (HIỂN THỊ) ---
    sql = """
        SELECT 
            p.MaPhong, p.Toa, p.Khu, p.SucChua, 
            (SELECT COUNT(*) FROM SinhVien WHERE Phong = p.MaPhong) as DangO, 
            p.TrangThai
        FROM Phong p ORDER BY p.MaPhong ASC
    """
    cursor.execute(sql)
    rooms = cursor.fetchall()

    cursor.execute(
        "SELECT MaSV, HoTen, NgayVao, Phong FROM SinhVien WHERE Phong IS NOT NULL")
    all_students = cursor.fetchall()

    student_map = {}
    for s in all_students:
        pid = s[3]
        if pid not in student_map:
            student_map[pid] = []
        student_map[pid].append({'masv': s[0], 'hoten': s[1], 'ngayvao': s[2].strftime(
            '%d/%m/%Y') if s[2] else '---'})

    conn.close()
    return render_template('admin_phong.html', rooms=rooms, students_by_room=student_map)


@app.route('/api/room/<room_id>/students')
def api_room_students(room_id):
    if not login_required('admin'):
        return {}, 403
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MaSV, HoTen, SoDienThoai, NgayVao FROM SinhVien WHERE Phong = ?", (room_id,))
    data = cursor.fetchall()
    conn.close()

    students = [{'masv': s[0], 'hoten': s[1], 'sdt': s[2], 'ngayvao': s[3].strftime(
        '%d/%m/%Y') if s[3] else ''} for s in data]
    return {'students': students}

# =================================================================
#  4. ADMIN: QUẢN LÝ HÓA ĐƠN (ĐÃ FIX LỖI & THÊM CHIA TIỀN ĐIỆN)
# =================================================================


@app.route('/admin/hoadon', methods=['GET', 'POST'])
def admin_hoadon():
    if not login_required('admin'):
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    # --- XỬ LÝ POST (THÊM, SỬA, XÓA) ---
    if request.method == 'POST':
        # Dùng thống nhất tên biến 'action'
        action = request.form.get('action')

        try:
            # 1. CHỨC NĂNG MỚI: TẠO HÓA ĐƠN ĐIỆN/NƯỚC THEO PHÒNG
            if action == 'create_room_bill':
                phong = request.form.get('phong_id')
                loai_phi = request.form.get('loai_phi')
                tong_tien = int(request.form.get('tong_tien'))
                thang = request.form.get('thang')
                nam = request.form.get('nam')
                noi_dung = f"{loai_phi} T{thang}/{nam}"

                # Lấy danh sách SV trong phòng (Dùng MaSV và Phong theo cấu trúc DB cũ của bạn)
                cursor.execute(
                    "SELECT MaSV FROM SinhVien WHERE Phong=?", (phong,))
                ds_sv = cursor.fetchall()
                so_nguoi = len(ds_sv)

                if so_nguoi > 0:
                    tien_moi_nguoi = tong_tien // so_nguoi
                    for sv in ds_sv:
                        # Tạo hóa đơn cho từng người
                        cursor.execute("""
                            INSERT INTO HoaDon (MaSV, LoaiHoaDon, SoTien, NgayLap, TrangThai)
                            VALUES (?, ?, ?, GETDATE(), N'Chưa thanh toán')
                        """, (sv[0], noi_dung, tien_moi_nguoi))

                    conn.commit()
                    flash(
                        f'✅ Đã chia {tong_tien:,}đ cho {so_nguoi} người phòng {phong}. Mỗi người: {tien_moi_nguoi:,}đ', 'success')
                else:
                    flash(
                        f'⚠️ Phòng {phong} hiện không có sinh viên nào!', 'warning')

            # 2. THÊM HÓA ĐƠN LẺ (Code cũ)
            elif action == 'add_single':
                masv = request.form.get('masv').strip().upper()
                cursor.execute(
                    "SELECT Count(*) FROM SinhVien WHERE MaSV=?", (masv,))
                if cursor.fetchone()[0] == 0:
                    flash('Mã SV không tồn tại!', 'danger')
                else:
                    cursor.execute("INSERT INTO HoaDon (MaSV, LoaiHoaDon, SoTien, NgayLap, TrangThai) VALUES (?, ?, ?, GETDATE(), N'Chưa thanh toán')",
                                   (masv, request.form.get('loai'), request.form.get('tien')))
                    conn.commit()
                    flash('Thêm hóa đơn thành công!', 'success')

            # 3. THÊM HÀNG LOẠT (Code cũ)
            elif action == 'add_batch':
                ten_phi = f"{request.form.get('loai_goc')} T{request.form.get('thang')}/{request.form.get('nam')}"
                tien = request.form.get('tien')
                cursor.execute(
                    "SELECT MaSV FROM SinhVien WHERE Phong IS NOT NULL AND Phong != ''")
                count = 0
                for s in cursor.fetchall():
                    cursor.execute(
                        "SELECT Count(*) FROM HoaDon WHERE MaSV=? AND LoaiHoaDon=?", (s[0], ten_phi))
                    if cursor.fetchone()[0] == 0:
                        cursor.execute(
                            "INSERT INTO HoaDon (MaSV, LoaiHoaDon, SoTien, NgayLap, TrangThai) VALUES (?, ?, ?, GETDATE(), N'Chưa thanh toán')", (s[0], ten_phi, tien))
                        count += 1
                conn.commit()
                flash(f'Đã tạo {count} hóa đơn hàng loạt!', 'success')

            # 4. THANH TOÁN HOẶC XÓA (Code cũ)
            elif action == 'pay' or action == 'delete':
                ids = request.form.getlist('chk_id')
                if ids:
                    ph = ','.join(['?'] * len(ids))
                    if action == 'pay':
                        cursor.execute(
                            f"UPDATE HoaDon SET TrangThai=N'Đã thanh toán', NgayThanhToan=GETDATE() WHERE MaHoaDon IN ({ph})", ids)
                        flash(f'Đã thu tiền {len(ids)} hóa đơn!', 'success')
                    else:
                        cursor.execute(
                            f"DELETE FROM HoaDon WHERE MaHoaDon IN ({ph})", ids)
                        flash(f'Đã xóa {len(ids)} hóa đơn!', 'success')
                    conn.commit()

        except Exception as e:
            conn.rollback()
            flash(f'Lỗi: {e}', 'danger')

        return redirect(url_for('admin_hoadon'))

   # --- XỬ LÝ GET (HIỂN THỊ DANH SÁCH & BỘ LỌC) ---
    import datetime
    today = datetime.date.today()

    # Lấy giá trị từ trình duyệt gửi lên, nếu không có thì lấy mặc định
    f_month = request.args.get('month', str(today.month))
    f_year = request.args.get('year', str(today.year))
    f_status = request.args.get('status', 'Tất cả')
    keyword = request.args.get('keyword', '').strip()

    # Câu lệnh SQL cơ bản (JOIN để lấy tên sinh viên và phòng)
    sql = """
        SELECT hd.MaHoaDon, sv.MaSV, sv.HoTen, sv.Phong, hd.LoaiHoaDon, hd.SoTien, hd.NgayLap, hd.TrangThai 
        FROM HoaDon hd 
        LEFT JOIN SinhVien sv ON hd.MaSV = sv.MaSV 
        WHERE 1=1
    """
    params = []

    # 1. Lọc theo Tháng (Nếu có)
    if f_month and f_month != '0':
        sql += " AND MONTH(hd.NgayLap) = ?"
        params.append(f_month)

    # 2. Lọc theo Năm
    if f_year:
        sql += " AND YEAR(hd.NgayLap) = ?"
        params.append(f_year)

    # 3. Lọc theo Trạng thái
    if f_status != 'Tất cả':
        sql += " AND hd.TrangThai = ?"
        params.append(f_status)

    # 4. Tìm kiếm theo từ khóa (Mã SV hoặc Tên)
    if keyword:
        sql += " AND (sv.MaSV LIKE ? OR sv.HoTen LIKE ?)"
        params.append(f"%{keyword}%")
        params.append(f"%{keyword}%")

    sql += " ORDER BY hd.MaHoaDon DESC"

    cursor.execute(sql, tuple(params))
    invoices = cursor.fetchall()

    # Tính toán lại thống kê dựa trên danh sách đã lọc
    stats = {'total': 0, 'collected': 0, 'debt': 0}
    for inv in invoices:
        amt = float(inv[5]) if inv[5] else 0
        stats['total'] += amt
        if inv[7] == u'Đã thanh toán':  # Dùng u để đảm bảo Unicode nếu cần
            stats['collected'] += amt
        else:
            stats['debt'] += amt

    # Lấy danh sách Phòng cho Modal
    cursor.execute(
        "SELECT DISTINCT Phong FROM SinhVien WHERE Phong IS NOT NULL AND Phong != '' ORDER BY Phong ASC")
    ds_phong = cursor.fetchall()

    conn.close()

    # Trả về giao diện kèm theo các giá trị lọc để giữ trạng thái trên thanh chọn
    return render_template('admin_hoadon.html',
                           invoices=invoices,
                           phongs=ds_phong,
                           stats=stats,
                           filters={'month': int(f_month), 'year': int(
                               f_year), 'status': f_status, 'keyword': keyword},
                           now=today)

# =================================================================
#  5. ADMIN: QUẢN LÝ THIẾT BỊ
# =================================================================


@app.route('/admin/device')
def admin_device():
    if not login_required('admin'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tb.MaThietBi, tb.TenThietBi, tb.MaPhong, p.Toa, p.Khu, tb.TrangThai, tb.NgayMua, tb.GiaTri
        FROM ThietBi tb LEFT JOIN Phong p ON tb.MaPhong = p.MaPhong ORDER BY tb.MaThietBi DESC
    """)
    devices = cursor.fetchall()
    cursor.execute("SELECT MaPhong FROM Phong ORDER BY MaPhong")
    rooms = [r[0] for r in cursor.fetchall()]
    conn.close()
    return render_template('admin_device.html', devices=devices, rooms=rooms)


@app.route('/admin/device/action', methods=['POST'])
def admin_device_action():
    if not login_required('admin'):
        return redirect(url_for('login'))
    action = request.form.get('action')
    try:
        conn = get_db()
        cursor = conn.cursor()
        if action == 'add':
            cursor.execute("INSERT INTO ThietBi (TenThietBi, MaPhong, NgayMua, GiaTri, TrangThai) VALUES (?, ?, ?, ?, ?)",
                           (request.form.get('ten'), request.form.get('phong'), request.form.get('ngay'), request.form.get('gia'), request.form.get('trangthai')))
            flash('Thêm thiết bị thành công!', 'success')
        elif action == 'update':
            cursor.execute("UPDATE ThietBi SET TenThietBi=?, MaPhong=?, NgayMua=?, GiaTri=?, TrangThai=? WHERE MaThietBi=?",
                           (request.form.get('ten'), request.form.get('phong'), request.form.get('ngay'), request.form.get('gia'), request.form.get('trangthai'), request.form.get('matb')))
            flash('Cập nhật thiết bị thành công!', 'success')
        elif action == 'delete':
            cursor.execute("DELETE FROM ThietBi WHERE MaThietBi=?",
                           (request.form.get('matb'),))
            flash('Xóa thiết bị thành công!', 'success')
        conn.commit()
    except Exception as e:
        flash(f'Lỗi: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('admin_device'))

# =================================================================
#  6. ADMIN: DANH SÁCH SV & DUYỆT ĐƠN & TÀI KHOẢN
# =================================================================


@app.route('/admin/students')
def admin_student_list():
    if not login_required('admin'):
        return redirect(url_for('login'))
    keyword = request.args.get('keyword', '').strip()
    conn = get_db()
    cursor = conn.cursor()
    sql = """
        SELECT sv.MaSV, sv.HoTen, sv.Phong, sv.SoDienThoai, sv.Email,
               (SELECT COUNT(*) FROM HoaDon WHERE MaSV = sv.MaSV AND TrangThai = N'Chưa thanh toán') as NoHD
        FROM SinhVien sv WHERE sv.MaSV LIKE ? OR sv.HoTen LIKE ? ORDER BY sv.MaSV
    """
    cursor.execute(sql, (f"%{keyword}%", f"%{keyword}%"))
    students = cursor.fetchall()
    conn.close()
    return render_template('admin_student_list.html', students=students, keyword=keyword)


@app.route('/api/student/<masv>')
def api_student_detail(masv):
    if not login_required('admin'):
        return "Access Denied", 403
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MaSV, HoTen, GioiTinh, NgaySinh, SoDienThoai, Email, DiaChi, Phong, Avatar, NgayVao FROM SinhVien WHERE MaSV=?", (masv,))
    data = cursor.fetchone()

    cursor.execute(
        "SELECT LoaiHoaDon, SoTien, NgayLap, TrangThai FROM HoaDon WHERE MaSV=? ORDER BY NgayLap DESC", (masv,))
    bills = [{'loai': b[0], 'tien': "{:,.0f}".format(b[1]), 'ngay': b[2].strftime(
        '%d/%m/%Y'), 'stt': b[3]} for b in cursor.fetchall()]
    conn.close()

    if data:
        ava = base64.b64encode(data[8]).decode('utf-8') if data[8] else None
        return {
            'masv': data[0], 'hoten': data[1], 'gioitinh': data[2],
            'ngaysinh': data[3].strftime('%d/%m/%Y') if data[3] else '',
            'sdt': data[4], 'email': data[5], 'diachi': data[6],
            'phong': data[7] if data[7] else 'Chưa có', 'ngayvao': data[9].strftime('%d/%m/%Y') if data[9] else '',
            'avatar': ava, 'bills': bills
        }
    return {}, 404


@app.route('/admin/approve', methods=['GET', 'POST'])
def admin_approve():
    if not login_required('admin'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        madon = request.form.get('madon')
        action = request.form.get('action')
        cursor.execute(
            "SELECT MaSV, MaPhong FROM DonDangKy WHERE MaDon=?", (madon,))
        don = cursor.fetchone()
        if don:
            masv, maphong = don
            if action == 'approve':
                cursor.execute(
                    "SELECT SoNguoiHienTai, SucChua FROM Phong WHERE MaPhong=?", (maphong,))
                phong = cursor.fetchone()
                if phong and phong[0] < phong[1]:
                    cursor.execute(
                        "UPDATE SinhVien SET Phong=?, NgayVao=GETDATE() WHERE MaSV=?", (maphong, masv))
                    cursor.execute(
                        "UPDATE Phong SET SoNguoiHienTai = SoNguoiHienTai + 1 WHERE MaPhong=?", (maphong,))
                    cursor.execute(
                        "UPDATE DonDangKy SET TrangThai=N'Đã duyệt' WHERE MaDon=?", (madon,))
                    if phong[0] + 1 >= phong[1]:
                        cursor.execute(
                            "UPDATE Phong SET TrangThai=N'Đầy' WHERE MaPhong=?", (maphong,))
                    conn.commit()
                    flash(
                        f'Đã duyệt cho {masv} vào phòng {maphong}', 'success')
                else:
                    flash(f'Phòng {maphong} đã đầy!', 'danger')
            else:
                cursor.execute(
                    "UPDATE DonDangKy SET TrangThai=N'Bị từ chối' WHERE MaDon=?", (madon,))
                conn.commit()
                flash('Đã từ chối đơn.', 'warning')

    cursor.execute("""
        SELECT d.MaDon, d.MaSV, s.HoTen, d.MaPhong, d.NgayGui, d.TrangThai
        FROM DonDangKy d JOIN SinhVien s ON d.MaSV = s.MaSV
        WHERE d.TrangThai = N'Chờ duyệt' ORDER BY d.NgayGui ASC
    """)
    ds_don = cursor.fetchall()
    conn.close()
    return render_template('admin_approve.html', ds_don=ds_don)


# --- [THAY THẾ HÀM admin_account TRONG app.py] ---

@app.route('/admin/account', methods=['GET', 'POST'])
def admin_account():
    if not login_required('admin'):
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    # --- XỬ LÝ POST (Thêm, Xóa, Reset - Giữ nguyên logic cũ của bạn) ---
    if request.method == 'POST':
        act = request.form.get('action')
        uid = request.form.get('user_id')

        # 1. RESET MẬT KHẨU
        if act == 'reset':
            cursor.execute("SELECT Username FROM Users WHERE UserID=?", (uid,))
            target = cursor.fetchone()
            if target:
                target_name = target[0].lower()
                current_user = session['username'].lower()
                if target_name == 'admin' and current_user != 'admin':
                    flash('⛔ CẢNH BÁO: Bạn không đủ quyền reset Super Admin!', 'danger')
                else:
                    cursor.execute(
                        "UPDATE Users SET Password='123456' WHERE UserID=?", (uid,))
                    conn.commit()
                    flash(
                        f'✅ Đã reset mật khẩu {target[0]} về "123456"', 'success')

        # 2. XÓA TÀI KHOẢN
        elif act == 'delete':
            cursor.execute("SELECT Username FROM Users WHERE UserID=?", (uid,))
            target = cursor.fetchone()
            if target:
                target_name = target[0].lower()
                if target_name == 'admin':
                    flash('⛔ CẢNH BÁO: Không thể xóa Super Admin!', 'danger')
                elif str(uid) == str(session['user_id']):
                    flash('⚠️ Không thể tự xóa chính mình!', 'warning')
                else:
                    try:
                        cursor.execute(
                            "DELETE FROM SinhVien WHERE UserID=?", (uid,))
                        cursor.execute(
                            "DELETE FROM QuanTriVien WHERE UserID=?", (uid,))
                        cursor.execute(
                            "DELETE FROM Users WHERE UserID=?", (uid,))
                        conn.commit()
                        flash(f'✅ Đã xóa tài khoản: {target[0]}', 'success')
                    except Exception as e:
                        conn.rollback()
                        flash(f'Lỗi xóa: {e}', 'danger')

        # 3. THÊM ADMIN
        elif act == 'add_admin':
            u = request.form['username'].strip()
            p = request.form['password'].strip()
            cursor.execute("SELECT Count(*) FROM Users WHERE Username=?", (u,))
            if cursor.fetchone()[0] > 0:
                flash(f'Tên đăng nhập "{u}" đã tồn tại!', 'danger')
            else:
                cursor.execute(
                    "INSERT INTO Users (Username, Password, Role) VALUES (?, ?, 'admin')", (u, p))
                new_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]
                cursor.execute(
                    "INSERT INTO QuanTriVien (HoTen, UserID) VALUES (?, ?)", (f"Admin {u}", new_id))
                conn.commit()
                flash(f'✅ Đã thêm Admin: {u}', 'success')

        return redirect(url_for('admin_account'))

    # --- XỬ LÝ GET (TÌM KIẾM & LỌC) ---
    keyword = request.args.get('keyword', '').strip()
    role_filter = request.args.get('role', 'all')

    # Câu lệnh SQL cơ bản
    sql = """
        SELECT u.UserID, u.Username, u.Role, 
               CASE WHEN u.Role='sinhvien' THEN sv.HoTen ELSE qtv.HoTen END as HoTen
        FROM Users u 
        LEFT JOIN SinhVien sv ON u.UserID = sv.UserID 
        LEFT JOIN QuanTriVien qtv ON u.UserID = qtv.UserID
        WHERE 1=1
    """
    params = []

    # 1. Nếu có từ khóa tìm kiếm
    if keyword:
        sql += " AND (u.Username LIKE ? OR sv.HoTen LIKE ? OR qtv.HoTen LIKE ?)"
        # Tìm gần đúng (%) trong Username hoặc Tên thật
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    # 2. Nếu có lọc theo vai trò
    if role_filter != 'all':
        sql += " AND u.Role = ?"
        params.append(role_filter)

    sql += " ORDER BY u.Role ASC, u.Username ASC"

    cursor.execute(sql, tuple(params))
    users = cursor.fetchall()
    conn.close()

    return render_template('admin_account.html', users=users, keyword=keyword, current_role=role_filter)


@app.route('/admin/student/import', methods=['GET', 'POST'])
def admin_student_import():
    if not login_required('admin'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        try:
            if 'manual_add' in request.form:
                masv = request.form['masv'].strip().upper()
                cursor.execute(
                    "SELECT Count(*) FROM SinhVien WHERE MaSV=?", (masv,))
                if cursor.fetchone()[0] > 0:
                    flash(f'Mã SV {masv} đã tồn tại!', 'danger')
                else:
                    cursor.execute("INSERT INTO Users (Username, Password, Role) VALUES (?, ?, 'sinhvien')", (
                        masv, request.form.get('password', '123456')))
                    uid = cursor.execute("SELECT @@IDENTITY").fetchone()[0]
                    cursor.execute("INSERT INTO SinhVien (MaSV, HoTen, GioiTinh, NgaySinh, SoDienThoai, Email, DiaChi, UserID) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                   (masv, request.form['hoten'], request.form['gioitinh'], request.form.get('ngaysinh') or None, request.form['sdt'], request.form['email'], request.form['diachi'], uid))
                    conn.commit()
                    flash('Thêm sinh viên thành công!', 'success')
            # Tìm đoạn này trong app.py và thay thế:
            elif 'excel_add' in request.form:
                file = request.files['file_excel']
                if file:
                    df = pd.read_excel(file)
                    df.columns = [c.strip().lower() for c in df.columns]
                    count = 0
                    for _, row in df.iterrows():
                        masv = str(row.get('masv', '')).strip().upper()
                        if not masv:
                            continue

                        cursor.execute(
                            "SELECT Count(*) FROM SinhVien WHERE MaSV=?", (masv,))
                        if cursor.fetchone()[0] == 0:
                            # 1. Tạo tài khoản
                            cursor.execute(
                                "INSERT INTO Users (Username, Password, Role) VALUES (?, '123456', 'sinhvien')", (masv,))
                            uid = cursor.execute(
                                "SELECT @@IDENTITY").fetchone()[0]

                            # 2. Thêm SV (Phải có NgaySinh ở đây mới hiện lên hồ sơ được)
                            sql = """
                                INSERT INTO SinhVien (MaSV, HoTen, GioiTinh, NgaySinh, SoDienThoai, Email, DiaChi, UserID) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """
                            cursor.execute(sql, (
                                masv,
                                str(row.get('hoten', '')),
                                row.get('gioitinh'),
                                # QUAN TRỌNG: Dòng này lấy từ Excel
                                row.get('ngaysinh'),
                                str(row.get('sdt')),
                                str(row.get('email')),
                                str(row.get('diachi')),
                                uid
                            ))
                            count += 1
                    conn.commit()
                    flash(
                        f'✅ Đã nhập thành công {count} sinh viên!', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Lỗi: {e}', 'danger')
    conn.close()
    return render_template('admin_student_import.html')


@app.route('/admin/profile', methods=['GET', 'POST'])
def admin_profile():
    if not login_required('admin'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        file = request.files['avatar']
        params = [request.form['hoten'], request.form['sdt'],
                  request.form['email'], request.form['diachi']]
        sql = "UPDATE QuanTriVien SET HoTen=?, SoDienThoai=?, Email=?, DiaChi=?"
        if file:
            sql += ", Avatar=?"
            params.append(file.read())
        sql += " WHERE UserID=?"
        params.append(session['user_id'])
        cursor.execute(sql, tuple(params))
        conn.commit()
        flash('Cập nhật hồ sơ thành công!', 'success')

    cursor.execute(
        "SELECT HoTen, SoDienThoai, Email, DiaChi, Avatar FROM QuanTriVien WHERE UserID=?", (session['user_id'],))
    data = cursor.fetchone()
    conn.close()
    if not data:
        return redirect(url_for('admin_dashboard'))
    ava = base64.b64encode(data[4]).decode('utf-8') if data[4] else None
    return render_template('admin_profile.html', info=data, ava=ava)


@app.route('/admin/fix', methods=['GET', 'POST'])
def admin_fix():
    if not login_required('admin'):
        return redirect(url_for('login'))
    conn = get_db()
    if request.method == 'POST':
        cost = float(request.form['cost'] or 0)
        stt = request.form['status']
        conn.cursor().execute("UPDATE YeuCauSuaChua SET TrangThai=?, ChiPhi=?, NgayXuLy=GETDATE() WHERE MaYeuCau=?",
                              (stt, cost, request.form['req_id']))
        if stt == 'Hoàn thành' and cost > 0:
            conn.cursor().execute("INSERT INTO HoaDon (MaSV, LoaiHoaDon, SoTien, NgayLap, TrangThai) VALUES (?, ?, ?, GETDATE(), N'Chưa thanh toán')",
                                  (request.form['ma_sv'], f"Phí sửa chữa (YC #{request.form['req_id']})", cost))
            flash(f'Đã tạo hóa đơn phạt {cost:,.0f}đ!', 'warning')
        conn.commit()
        flash('Đã cập nhật trạng thái!', 'success')

    cursor = conn.cursor()
    cursor.execute(
        "SELECT MaYeuCau, MaSV, LoaiThietBi, MucDo, TrangThai, MoTa, NgayGui, HinhAnh, ChiPhi FROM YeuCauSuaChua ORDER BY NgayGui DESC")
    reqs = [{'id': r[0], 'masv': r[1], 'tb': r[2], 'lv': r[3], 'stt': r[4], 'desc': r[5], 'date': r[6],
             'img': base64.b64encode(r[7]).decode('utf-8') if r[7] else None, 'cost': r[8]} for r in cursor.fetchall()]
    conn.close()
    return render_template('admin_fix.html', reqs=reqs)


@app.route('/admin/search')
def admin_search():
    if not login_required('admin'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sv.MaSV, sv.HoTen, sv.Phong, sv.SoDienThoai, sv.DiaChi, (SELECT COUNT(*) FROM HoaDon WHERE MaSV = sv.MaSV AND TrangThai = N'Chưa thanh toán') FROM SinhVien sv")
    res = cursor.fetchall()
    conn.close()
    return render_template('admin_search.html', results=res)


@app.route('/admin/excel')
def export_excel():
    conn = get_db()
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        pd.read_sql("SELECT * FROM SinhVien", conn).to_excel(writer,
                                                             sheet_name='SinhVien', index=False)
        pd.read_sql("SELECT * FROM Phong", conn).to_excel(writer,
                                                          sheet_name='Phong', index=False)
        pd.read_sql("SELECT * FROM HoaDon", conn).to_excel(writer,
                                                           sheet_name='HoaDon', index=False)
    conn.close()
    out.seek(0)
    return send_file(out, download_name='DuLieu_KTX.xlsx', as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# =================================================================
#  7. SINH VIÊN
# =================================================================


@app.route('/student/home')
def student_home():
    if not login_required('sinhvien'):
        return redirect(url_for('login'))
    masv = session['masv']
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT HoTen, Phong, NgayVao, Avatar FROM SinhVien WHERE MaSV=?", (masv,))
    info = cur.fetchone()
    cur.execute(
        "SELECT * FROM HoaDon WHERE MaSV=? AND TrangThai=N'Chưa thanh toán'", (masv,))
    bills = cur.fetchall()
    mates = []
    if info and info[1]:
        cur.execute(
            "SELECT HoTen, SoDienThoai FROM SinhVien WHERE Phong=? AND MaSV!=?", (info[1], masv))
        mates = cur.fetchall()
    conn.close()

    ava = base64.b64encode(info[3]).decode('utf-8') if info[3] else None
    now_str = datetime.datetime.now().strftime("%d/%m/%Y")
    return render_template('student_home.html', info=info, bills=bills, mates=mates, ava=ava, now=now_str)


@app.route('/student/profile', methods=['GET', 'POST'])
def student_profile():
    if not login_required('sinhvien'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        file = request.files['avatar']
        params = [request.form['sdt'],
                  request.form['email'], request.form['diachi']]
        sql = "UPDATE SinhVien SET SoDienThoai=?, Email=?, DiaChi=?"
        if file:
            sql += ", Avatar=?"
            params.append(file.read())
        sql += " WHERE MaSV=?"
        params.append(session['masv'])
        cursor.execute(sql, tuple(params))
        conn.commit()
        flash('Đã cập nhật hồ sơ!', 'success')

    cursor.execute(
        "SELECT MaSV, HoTen, GioiTinh, NgaySinh, SoDienThoai, Email, DiaChi, Phong, NgayVao, Avatar FROM SinhVien WHERE MaSV=?", (session['masv'],))
    data = cursor.fetchone()
    conn.close()
    ava = base64.b64encode(data[9]).decode(
        'utf-8') if data and data[9] else None
    return render_template('student_profile.html', sv=data, ava=ava)


@app.route('/student/roommates')
def student_roommates():
    if not login_required('sinhvien'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT Phong FROM SinhVien WHERE MaSV=?",
                   (session['masv'],))
    res = cursor.fetchone()
    phong = res[0] if res else None
    mates = []
    if phong:
        cursor.execute(
            "SELECT MaSV, HoTen, SoDienThoai, DiaChi FROM SinhVien WHERE Phong=? AND MaSV!=?", (phong, session['masv']))
        mates = cursor.fetchall()
    conn.close()
    return render_template('student_roommates.html', mates=mates, phong=phong)


@app.route('/student/payment')
def student_payment():
    if not login_required('sinhvien'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MaHoaDon, LoaiHoaDon, SoTien, NgayLap, NgayThanhToan, TrangThai FROM HoaDon WHERE MaSV=? ORDER BY NgayLap DESC", (session['masv'],))
    history = cursor.fetchall()
    conn.close()
    return render_template('student_payment.html', history=history)


@app.route('/student/pay', methods=['POST'])
def student_pay():
    if not login_required('sinhvien'):
        return redirect(url_for('login'))
    try:
        conn = get_db()
        conn.cursor().execute("UPDATE HoaDon SET TrangThai = N'Đã thanh toán', NgayThanhToan = GETDATE() WHERE MaHoaDon = ? AND MaSV = ?",
                              (request.form.get('ma_hd'), session['masv']))
        conn.commit()
        flash('Thanh toán thành công!', 'success')
    except Exception as e:
        flash(f'Lỗi: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('student_payment'))


@app.route('/student/room', methods=['GET', 'POST'])
def student_room():
    if not login_required('sinhvien'):
        return redirect(url_for('login'))
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'POST':
        if 'return_room' in request.form:
            cur.execute("SELECT Phong FROM SinhVien WHERE MaSV=?",
                        (session['masv'],))
            phong = cur.fetchone()[0]
            if phong:
                cur.execute(
                    "UPDATE SinhVien SET Phong=NULL, NgayVao=NULL WHERE MaSV=?", (session['masv'],))
                cur.execute(
                    "UPDATE Phong SET SoNguoiHienTai = SoNguoiHienTai - 1 WHERE MaPhong=?", (phong,))
                cur.execute(
                    "UPDATE Phong SET TrangThai=N'Trống' WHERE MaPhong=? AND SoNguoiHienTai < SucChua", (phong,))
                conn.commit()
                flash(f'Đã trả phòng {phong}!', 'success')
            else:
                flash('Chưa có phòng!', 'warning')
        elif 'book_room' in request.form:
            cur.execute("SELECT Phong FROM SinhVien WHERE MaSV=?",
                        (session['masv'],))
            if cur.fetchone()[0]:
                flash('Bạn đang ở phòng rồi!', 'warning')
            else:
                cur.execute("INSERT INTO DonDangKy (MaSV, MaPhong, TrangThai, NgayGui) VALUES (?, ?, N'Chờ duyệt', GETDATE())",
                            (session['masv'], request.form['room_id']))
                conn.commit()
                flash('Đã gửi đơn đăng ký!', 'info')

    cur.execute(
        "SELECT MaPhong, Toa, Khu, SucChua, SoNguoiHienTai FROM Phong WHERE TrangThai=N'Trống'")
    rooms = cur.fetchall()
    cur.execute("SELECT Phong FROM SinhVien WHERE MaSV=?", (session['masv'],))
    curr = cur.fetchone()[0]
    conn.close()
    return render_template('student_room.html', rooms=rooms, current_room=curr)


@app.route('/student/fix', methods=['GET', 'POST'])
def student_fix():
    if not login_required('sinhvien'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        f = request.files['image']
        conn = get_db()
        conn.cursor().execute("INSERT INTO YeuCauSuaChua (MaSV, MoTa, LoaiThietBi, MucDo, TrangThai, NgayGui, HinhAnh) VALUES (?, ?, ?, ?, N'Chờ xử lý', GETDATE(), ?)",
                              (session['masv'], request.form['mota'], request.form['thietbi'], request.form['mucdo'], f.read() if f else None))
        conn.commit()
        conn.close()
        flash('Đã gửi yêu cầu!', 'success')
        return redirect(url_for('student_home'))
    return render_template('student_fix.html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
