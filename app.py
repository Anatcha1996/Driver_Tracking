from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import pytz
import os
from dotenv import load_dotenv

# โหลด .env
load_dotenv()

# สร้างแอป Flask
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or os.urandom(24)

# ตั้งค่า Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ตั้งเวลาไทย
THAI_TZ = pytz.timezone('Asia/Bangkok')
def to_thai_time(dt_utc):
    if dt_utc is None:
        return None
    if dt_utc.tzinfo is None:
        dt_utc = pytz.utc.localize(dt_utc)
    return dt_utc.astimezone(THAI_TZ)




# ----- Models -----
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    role = db.Column(db.String(20))  # 'admin' หรือ 'driver'
    locations = db.relationship('Location', backref='user', lazy=True, cascade="all, delete-orphan")
    attendances = db.relationship('Attendance', backref='user', lazy=True, cascade="all, delete-orphan")

    

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    checkin_time = db.Column(db.DateTime)
    checkin_lat = db.Column(db.Float)
    checkin_lon = db.Column(db.Float)
    checkout_time = db.Column(db.DateTime)
    checkout_lat = db.Column(db.Float)
    checkout_lon = db.Column(db.Float)

# ----- Decorator ตรวจสอบล็อกอิน -----
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ----- สร้างตารางและ Admin เริ่มต้น -----
@app.before_request
def setup():
    if not hasattr(app, 'tables_created'):
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('admin123'),
                phone='0634463873',
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
        app.tables_created = True


# ----- Routes -----
# จัดการผู้ใช้ (เฉพาะแอดมิน)
@app.route('/admin/manage_users')
@login_required
def manage_users():
    if session.get('role') != 'admin':
        return "Access denied"
    users = User.query.all()
    return render_template('admin_manage_users.html', users=users)


@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if session.get('role') != 'admin':
        return "Access denied"
    
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.phone = request.form['phone']
        user.role = request.form['role']
        db.session.commit()
        return redirect(url_for('manage_users'))
    
    return render_template('admin_edit_user.html', user=user)


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if session.get('role') != 'admin':
        return "Access denied"
    
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        return "ไม่สามารถลบผู้ดูแลระบบหลักได้"
    
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('manage_users'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        phone = request.form.get('phone') or ''  # รับค่าจากฟอร์ม
        role = request.form.get('role') or 'driver'

        if password != confirm_password:
            error = 'รหัสผ่านไม่ตรงกัน'
        elif User.query.filter_by(username=username).first():
            error = 'ชื่อผู้ใช้นี้ถูกใช้แล้ว'
        else:
            new_user = User(
                username=username,
                password=generate_password_hash(password),
                phone=phone,
                role=role
            )
            db.session.add(new_user)
            db.session.commit()
            flash('สมัครสมาชิกสำเร็จ')
            return redirect(url_for('login'))

    return render_template('register.html', error=error)




# หน้าแรก: เลือกไป dashboard ตาม role
@app.route('/')
def index():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if not user:
            session.clear()  # เคลียร์ session ที่ไม่ถูกต้อง
            return redirect(url_for('login'))
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user.role == 'driver':
            return redirect(url_for('checkin'))
        else:
            return f"Role ไม่ถูกต้อง: {user.role}"
    return redirect(url_for('login'))

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        session.clear()
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('index'))
        else:
            error = 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'
    return render_template('login.html', error=error)

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Admin Dashboard
@app.route('/admin')
@login_required
def admin_dashboard():
    if session.get('role') != 'admin':
        return "Access denied"
    drivers = User.query.filter_by(role='driver').all()
    return render_template('admin_dashboard.html', drivers=drivers)

from flask import flash

# หน้าแก้ไขรหัสผ่านผู้ใช้ (Admin ใช้)
@app.route('/admin/reset_password/<int:user_id>', methods=['GET', 'POST'])
@login_required
def reset_password(user_id):
    if session.get('role') != 'admin':
        return "Access denied"
    
    user = User.query.get(user_id)
    if not user:
        return "User not found"
    
    error = None
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            error = 'รหัสผ่านใหม่ไม่ตรงกัน'
        elif len(new_password) < 6:
            error = 'รหัสผ่านต้องมีความยาวอย่างน้อย 6 ตัวอักษร'
        else:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash('รีเซ็ตรหัสผ่านสำเร็จแล้ว')
            return redirect(url_for('manage_users'))
    
    return render_template('reset_password.html', user=user, error=error)

# Admin ดูรายงานชั่วโมงทำงาน
@app.route('/admin/worklog')
@login_required
def admin_worklog():
    if session.get('role') != 'admin':
        return "Access denied"
    
    attendances = Attendance.query.order_by(Attendance.checkin_time.desc()).all()
    
    logs = []
    for a in attendances:
        logs.append({
            'id': a.id,
            'user': a.user,
            'checkin_time': to_thai_time(a.checkin_time),
            'checkout_time': to_thai_time(a.checkout_time),
            'date': to_thai_time(a.checkin_time).date() if a.checkin_time else None
        })

    return render_template('admin_worklog.html', logs=logs)


@app.route('/admin/delete_attendance/<int:id>', methods=['POST'])
@login_required
def delete_attendance(id):
    if session.get('role') != 'admin':
        return "Access denied"
    record = Attendance.query.get(id)
    if record:
        db.session.delete(record)
        db.session.commit()
    return redirect(url_for('admin_worklog'))


# Driver หน้าเช็กอิน/เช็กเอาต์
@app.route('/checkin')
@login_required
def checkin():
    if session.get('role') != 'driver':
        return "Access denied"
    user_id = session['user_id']
    attendance = Attendance.query.filter_by(user_id=user_id).order_by(Attendance.checkin_time.desc()).first()

    # แปลงเวลา UTC → เวลาไทย
    if attendance:
        if attendance.checkin_time:
            attendance.checkin_time = to_thai_time(attendance.checkin_time)
        if attendance.checkout_time:
            attendance.checkout_time = to_thai_time(attendance.checkout_time)

    return render_template('checkin.html', attendance=attendance)


# API เช็กอิน
@app.route('/checkin', methods=['POST'])
@login_required
def do_checkin():
    if session.get('role') != 'driver':
        return jsonify({"error": "Access denied"}), 403
    data = request.json
    user_id = session['user_id']

    # สร้าง record ใหม่ เช็กอิน
    attendance = Attendance(
        user_id=user_id,
        checkin_time=datetime.utcnow(),
        checkin_lat=data.get('lat'),
        checkin_lon=data.get('lon')
    )
    db.session.add(attendance)
    db.session.commit()
    return jsonify({'message': 'เช็กอินสำเร็จ'})

# API เช็กเอาต์
@app.route('/checkout', methods=['POST'])
@login_required
def do_checkout():
    if session.get('role') != 'driver':
        return jsonify({"error": "Access denied"}), 403
    data = request.json
    user_id = session['user_id']

    # ค้นหา record ล่าสุดที่ยังไม่มี checkout
    attendance = Attendance.query.filter_by(user_id=user_id, checkout_time=None).order_by(Attendance.checkin_time.desc()).first()
    if not attendance:
        return jsonify({'message': 'ไม่พบข้อมูลเช็กอินที่ยังไม่ได้เช็กเอาต์'}), 404

    attendance.checkout_time = datetime.utcnow()
    attendance.checkout_lat = data.get('lat')
    attendance.checkout_lon = data.get('lon')
    db.session.commit()
    return jsonify({'message': 'เช็กเอาต์สำเร็จ'})

# Driver ส่งตำแหน่ง (แบบฟอร์ม POST)
@app.route('/driver/location_submit', methods=['GET', 'POST'])
@login_required
def driver_location_submit():
    if session.get('role') != 'driver':
        return "Access denied"
    if request.method == 'POST':
        lat = request.form.get('latitude')
        lng = request.form.get('longitude')
        if lat and lng:
            try:
                lat = float(lat)
                lng = float(lng)
                location = Location(user_id=session['user_id'], latitude=lat, longitude=lng)
                db.session.add(location)
                db.session.commit()
                return render_template('location_submit.html', message="อัปเดตตำแหน่งเรียบร้อยแล้ว")
            except ValueError:
                return render_template('location_submit.html', error="กรุณากรอกค่าพิกัดให้ถูกต้อง")
        else:
            return render_template('location_submit.html', error="กรุณากรอกพิกัดให้ครบ")
    return render_template('location_submit.html')

@app.route('/driver/update_location', methods=['POST'])
@login_required
def update_location():
    data = request.get_json()
    lat = data.get('latitude')
    lng = data.get('longitude')
    if lat and lng:
        location = Location(user_id=session['user_id'], latitude=lat, longitude=lng)
        db.session.add(location)
        db.session.commit()
        return jsonify({"message": "ตำแหน่งอัปเดตแล้ว"})
    return jsonify({"error": "ข้อมูลไม่ครบ"}), 400


@app.route('/driver/location_submit_auto', methods=['GET', 'POST'])
@login_required
def driver_location_submit_auto():  # ชื่อต้องไม่ซ้ำ
    return render_template('location_submit_auto.html')


@app.route('/all_drivers_map')
@login_required
def all_drivers_map():
    if session.get('role') != 'admin':
        return "Access denied"
    drivers = User.query.filter_by(role='driver').all()
    return render_template('all_drivers_map.html', drivers=drivers)

@app.route('/api/all_drivers_locations')
@login_required
def api_all_drivers_locations():
    if session.get('role') != 'admin':
        return jsonify({"error": "Access denied"}), 403

    # ดึงตำแหน่งล่าสุดของพนักงานขับรถทุกคน (สมมติ Location model มี user_id, latitude, longitude, timestamp)
    # ต้องเลือกตำแหน่งล่าสุดของแต่ละ user
    # ตัวอย่างง่าย ๆ (ปรับตามฐานข้อมูลจริง)
    subquery = db.session.query(
        Location.user_id,
        db.func.max(Location.timestamp).label('max_time')
    ).group_by(Location.user_id).subquery()

    locations = db.session.query(Location, User).join(User, Location.user_id == User.id)\
        .join(subquery, (Location.user_id == subquery.c.user_id) & (Location.timestamp == subquery.c.max_time))\
        .all()

    data = []
    for loc, user in locations:
        data.append({
            'lat': loc.latitude,
            'lng': loc.longitude,
            'timestamp': loc.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'username': user.username
        })

    return jsonify(data)


# แอดมินดูตำแหน่งเรียลไทม์ของพนักงาน
@app.route('/driver_locations_realtime/<int:user_id>')
@login_required
def driver_locations_realtime(user_id):
    if session.get('role') != 'admin':
        return "Access denied"
    user = User.query.get(user_id)
    if not user:
        return "User not found"
    return render_template('driver_locations_realtime.html', user=user)

# API คืนตำแหน่งล่าสุด 10 จุดของพนักงาน (แอดมินใช้)
@app.route('/api/driver_locations/<int:user_id>')
@login_required
def api_driver_locations(user_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Access denied"}), 403
    locations = Location.query.filter_by(user_id=user_id).order_by(Location.timestamp.desc()).limit(20).all()
    data = [{
        'lat': loc.latitude,
        'lng': loc.longitude,
        'timestamp': loc.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for loc in locations]
    return jsonify(data)

@app.route('/api/route/<int:attendance_id>')
@login_required
def api_driver_route(attendance_id):
    # ตรวจสิทธิ์
    if session.get('role') != 'admin':
        return jsonify({"error": "Access denied"}), 403

    # ดึงข้อมูล attendance
    attendance = Attendance.query.get_or_404(attendance_id)
    if not attendance.checkout_time:
        return jsonify({"error": "ยังไม่มีเวลาเช็กเอาต์"}), 400

    # ดึงตำแหน่งในช่วงเวลาเช็กอิน - เช็กเอาต์
    locations = Location.query.filter(
        Location.user_id == attendance.user_id,
        Location.timestamp >= attendance.checkin_time,
        Location.timestamp <= attendance.checkout_time
    ).order_by(Location.timestamp.asc()).all()

    data = [{
        'lat': loc.latitude,
        'lng': loc.longitude,
        'timestamp': loc.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for loc in locations]

    return jsonify(data)


@app.route('/admin/view_route/<int:attendance_id>')
@login_required
def view_route(attendance_id):
    return render_template('admin_view_route.html', attendance_id=attendance_id)

@app.route('/admin/view_route_range/<int:user_id>', methods=['GET', 'POST'])
@login_required
def view_route_range(user_id):
    if session.get('role') != 'admin':
        return "Access denied"

    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        start = request.form.get('start_date')
        end = request.form.get('end_date')
        return redirect(url_for('show_route_map_range', user_id=user_id, start=start, end=end))

    return render_template('view_route_range.html', user=user)

@app.route('/admin/show_route_map_range/<int:user_id>')
@login_required
def show_route_map_range(user_id):
    if session.get('role') != 'admin':
        return "Access denied"
    return render_template('admin_route_range_map.html', user_id=user_id, start=request.args.get('start'), end=request.args.get('end'))
@app.route('/api/route_range/<int:user_id>')
@login_required
def api_route_range(user_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Access denied"}), 403

    start_str = request.args.get('start')
    end_str = request.args.get('end')
    try:
        start = datetime.strptime(start_str, '%Y-%m-%d')
        end = datetime.strptime(end_str, '%Y-%m-%d')
        end = end.replace(hour=23, minute=59, second=59)
    except:
        return jsonify({"error": "รูปแบบวันที่ไม่ถูกต้อง"}), 400

    locations = Location.query.filter(
        Location.user_id == user_id,
        Location.timestamp >= start,
        Location.timestamp <= end
    ).order_by(Location.timestamp.asc()).all()

    data = [{
        'lat': loc.latitude,
        'lng': loc.longitude,
        'timestamp': loc.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for loc in locations]

    return jsonify(data)


if __name__ == '__main__':
    app.run(debug=True)
