from flask import Flask, render_template, request, url_for, flash, redirect, session    
from flask_mysqldb import MySQL, MySQLdb
import MySQLdb.cursors
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from datetime import datetime,timedelta
import smtplib
from email.mime.text import MIMEText
import secrets, smtplib,qrcode, os,re

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
    

    #------------------CONFICURACION FLASK Y MYSQL-----------

app = Flask(__name__)
app.secret_key = 'colegiocarlosalban'
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'bdpython' 
mysql = MySQL(app)

#-------------------FUCIONES AUXILIARES-------------------
def generar_token(email):
    token=secrets.token_urlsafe(32)
    expiry=datetime.now() + timedelta(hours=1)
    cur =mysql.connection.cursor()
    cur.execute("UPDATE usuarios SET reset_token=%s, token_expiry=%s WHERE username=%s",(token,expiry,email))
    mysql.connection.commit()
    cur.close()
    return token 
def enviar_correo_reset(email,token):
    enlace = url_for('reset', token=token,_external=True)
    cuerpo =f"""
Hola,solicitaste recuperar tu contraseña.
Haz click en el siguiente enlace:
{enlace}
Este enlace expira en 1 hora.
Si no lo solicitaste, ignora este mensaje.
"""
    remitente='pythoncontrasenas@gmail.com'
    clave='yqqp dtpo zmwv yuin'
    mensaje =MIMEText(cuerpo)
    mensaje['Subject']='Recuperar comtraseña' 
    mensaje['from']='pythoncontrasenas@gmail.com'
    mensaje['to']=email
    server =smtplib.SMTP('smtp.gmail.com',587)
    server.starttls()
    server.login(remitente,clave)
    server.sendmail(remitente,email,mensaje.as_string())
    server.quit()
def enviar_qr_por_correo(email,nombre,qr_path):
    remitente =  'pythoncontrasenas@gmail.com'
    clave = 'yqqp dtpo zmwv yuin'
    asunto = 'Tu código QR de registro'
    cuerpo = f"""Hola {nombre},
    
Te has registrado correctamente en el sistema
Adjunto encontraras tu codigo QR personal para registrar asistencias
por favor, guardalo o impremelo para usarlo al ingresar o salir 
Saludos,
Equipo de control de asistencias
"""
    mensaje = MIMEMultipart()
    mensaje['From'] = remitente
    mensaje['To'] = email
    mensaje['Subject'] = asunto
    mensaje.attach(MIMEText(cuerpo, 'plain'))
    if not os.path.exists(qr_path):
        raise FileNotFoundError(f"QR no encontrado: {qr_path}")
    with open(qr_path, 'rb') as adjunto:
        parte = MIMEBase('application', 'octet-stream')    
        parte.set_payload(adjunto.read())
        encoders.encode_base64(parte)
        parte.add_header('Content-Disposition', f'attachment; filename= {os.path.basename(qr_path)}')
        mensaje.attach(parte)
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(remitente, clave)
    server.sendmail(remitente, email, mensaje.as_string())
    server.quit()
    
#-------------------RUTAS-----------------------
@app.route('/')
def index():
    return render_template('index.html')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_ingresada= request.form['password']
        cur = mysql.connection.cursor()
        cur.execute("""
        SELECT u.idUsuario, u.nombre, u.password, r.nombreRol
        FROM usuarios u
        JOIN usuario_rol ur ON u.idUsuario= ur.idUsuario
        JOIN roles r ON ur.idRol = r.idRol
        WHERE u.username = %s
        """,(username,))
        usuario = cur.fetchone()
        if usuario and check_password_hash(usuario[2], password_ingresada):
            session['usuario'] = usuario[1]
            session['idUsuario'] = usuario[0]
            session['rol'] = usuario[3]
            flash(f"¡Bienvenido {usuario[1]}!")
            cur.execute("""
            INSERT INTO registro_login(idUsuario, fecha)
            VALUES (%s, NOW())
            """, (usuario[0],))
            mysql.connection.commit()
            cur.close
            if usuario[3] == 'admin':
                return redirect(url_for('dashboard'))
            elif usuario[3] == 'usuario':
                return redirect(url_for('movimientos'))
            else:
                flash('Rol de usuario no reconocido.')
                return redirect(url_for('login'))
        else:
            flash('Usuario o contraseña incorrecta.')
    return render_template('login.html')
@app.route('/logout')
def logout():
    session.clear()
    flash('Sesion cerrada correctamente.')
    return redirect(url_for('login'))
                            
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        username = request.form['username']
        password = request.form['password']
        if not re.match(r'[^@]+@[^@]+\.[^@]+', username):
            flash("Correo electrónico inválido.")
            return render_template('registro.html')
        cur = mysql.connection.cursor()
        try:
            # Verificar si el usuario ya existe
            cur.execute("SELECT idUsuario FROM usuarios WHERE username = %s", (username,))
            if cur.fetchone():
                flash("El correo ya está registrado.")
                return render_template('registro.html')
            # Insertar usuario
            hash_pw = generate_password_hash(password)
            cur.execute("""
                INSERT INTO usuarios(nombre, apellido, username, password)
                VALUES (%s, %s, %s, %s)
            """, (nombre, apellido, username, hash_pw))
            mysql.connection.commit()
            user_id = cur.lastrowid
            # Crear carpeta de QR si no existe
            qr_folder = os.path.join(app.root_path, 'static', 'qr')
            os.makedirs(qr_folder, exist_ok=True)
            # Generar QR
            qr_data = f"usuario:{user_id}"
            img = qrcode.make(qr_data)
            qr_filename = f"qr_{user_id}.png"
            qr_path = os.path.join(qr_folder, qr_filename)
            img.save(qr_path)
            qr_web_path = f"/static/qr/{qr_filename}"
            # Validar que el QR se guardó
            if not os.path.exists(qr_path):
                raise FileNotFoundError(f"QR no encontrado: {qr_path}")
            # Guardar QR en la base de datos
            cur.execute("UPDATE usuarios SET qr_path = %s WHERE idUsuario = %s", (qr_web_path, user_id))
            mysql.connection.commit()
            # Asignar rol
            cur.execute("INSERT INTO usuario_rol(idUsuario, idRol) VALUES (%s, %s)", (user_id, 2))
            mysql.connection.commit()
            # Enviar correo
            try:
                enviar_qr_por_correo(username, nombre, qr_path)
                flash("Usuario registrado y QR enviado al correo.")
            except Exception as e:
                print(f"Error al enviar correo: {e}")
                flash("Usuario creado, pero hubo un problema al enviar el QR por correo.")
            return redirect(url_for('login'))
        except Exception as e:
            print(f"Error al registrar usuario: {e}")
            flash("Ocurrió un error al registrar el usuario.")
        finally:
            cur.close()
    return render_template('registro.html')
@app.route('/forgot', methods=['GET','POST'])
def forgot():
    if request.method=='POST':
        email=request.form['email']
        cur = mysql.connection.cursor()
        cur.execute("SELECT idUsuario FROM usuarios WHERE username=%s",(email,))
        existe =cur.fetchone()
        cur.close()
        if not existe:
            flash("este correo no esta registrado")
            return redirect(url_for('forgot'))
            
        token = generar_token(email)
        enviar_correo_reset(email,token)
        flash("Te enviamos un correo para restablecer tu contraseña")
        return redirect(url_for('login'))
        
    return render_template('forgot.html')
@app.route('/reset/<token>', methods =['GET','POST'])
def reset(token):
    cur = mysql.connection.cursor()
    cur.execute("SELECT idUsuario, token_expiry FROM usuarios WHERE reset_token = %s", (token,))
    usuario = cur.fetchone()
    cur.close()
    if not usuario or datetime.now() > usuario[1]:
        flash("Token inválido o expirado.")
        return redirect(url_for('forgot'))
    if request.method == 'POST':
        nuevo_password = request.form['password']
        hash_nueva = generate_password_hash(nuevo_password)
        cur = mysql.connection.cursor()
        cur.execute("UPDATE usuarios SET password=%s, reset_token=NULL, token_expiry=NULL WHERE idUsuario=%s", (hash_nueva, usuario[0]))
        mysql.connection.commit()
        cur.close()
        flash("Contraseña actualizada correctamente.")
        return redirect(url_for('login'))
    
    return render_template('reset.html', token=token)
@app.route('/editar_usuario/<int:id>', methods=['POST'])
def editar_usuario(id):
    nombre = request.form['nombre']
    apellido = request.form['apellido']
    username = request.form['correo']
    rol = request.form['rol']  # Este es el idRol, no el nombre del rol

    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        # Actualizar datos personales
        cur.execute("""
            UPDATE usuarios
            SET nombre=%s, apellido=%s, username=%s
            WHERE idUsuario=%s
        """, (nombre, apellido, username, id))

        # Actualizar rol en tabla usuario_rol
        cur.execute("""
            UPDATE usuario_rol
            SET idRol=%s
            WHERE idUsuario=%s
        """, (rol, id))

        mysql.connection.commit()
        cur.close()
        flash('Usuario actualizado correctamente.')

    except Exception as e:
        print("Error al actualizar usuario:", e)
        flash('Error al actualizar usuario.')

    return redirect(url_for('dashboard'))

@app.route('/agregar_usuario', methods=['POST'])
def agregar_usuario():
    nombre = request.form['nombre']
    apellido = request.form['apellido']
    username = request.form['username']
    idRol = request.form['rol']

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO usuarios (nombre, apellido, username)
        VALUES (%s, %s, %s)
    """, (nombre, apellido, username))
    mysql.connection.commit()

    id_usuario = cur.lastrowid
    cur.execute("""
        INSERT INTO usuario_rol (idUsuario, idRol)
        VALUES (%s, %s)
    """, (id_usuario, idRol))
    mysql.connection.commit()
    cur.close()

    flash('Usuario agregado correctamente.')
    return redirect(url_for('dashboard'))

@app.route('/eliminar_usuario/<int:id>', methods=['POST'])
def eliminar_usuario(id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM usuario_rol WHERE idUsuario=%s", (id,))
        cur.execute("DELETE FROM usuarios WHERE idUsuario=%s", (id,))
        mysql.connection.commit()
        cur.close()
        flash('Usuario eliminado correctamente.')
    except Exception as e:
        print("Error al eliminar usuario:", e)
        flash('Error al eliminar usuario.')
    
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session or session.get('rol') != 'admin':
        flash('Acceso denegado. Solo administradores.')
        return redirect(url_for('login'))
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
    SELECT u.idUsuario, u.nombre, u.apellido, u.username, r.nombreRol
    FROM usuarios u
    JOIN usuario_rol ur ON u.idUsuario = ur.idUsuario
    JOIN roles r ON ur.idRol = r.idRol
    """)
    usuarios = cur.fetchall()
    cur.close()
    return render_template('dashboard.html', usuarios=usuarios)

# RUTA: Mostrar registro de entradas y salidas

@app.route('/movimientos')
def movimientos():
    if 'usuario' not in session:
        flash('Debe iniciar sesión para acceder.')
        return redirect(url_for('login'))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT m.idMovimiento, m.tipo, m.fecha, m.hora, u.nombre, u.apellido
        FROM movimientos m
        JOIN usuarios u ON m.idUsuario = u.idUsuario
        ORDER BY m.fecha DESC, m.hora DESC
    """)
    movimientos = cur.fetchall()
    cur.close()

    return render_template('movimientos.html', movimientos=movimientos)

# RUTA: Registrar entrada

@app.route('/registrar_entrada/<int:id_usuario>', methods=['POST'])
def registrar_entrada(id_usuario):
    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO movimientos (idUsuario, tipo, fecha, hora)
        VALUES (%s, 'Entrada', CURDATE(), CURTIME())
    """, (id_usuario,))
    mysql.connection.commit()
    cur.close()
    flash('Entrada registrada correctamente.')
    return redirect(url_for('movimientos'))

# RUTA: Registrar salida

@app.route('/registrar_salida/<int:id_usuario>', methods=['POST'])
def registrar_salida(id_usuario):
    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO movimientos (idUsuario, tipo, fecha, hora)
        VALUES (%s, 'Salida', CURDATE(), CURTIME())
    """, (id_usuario,))
    mysql.connection.commit()
    cur.close()
    flash('Salida registrada correctamente.')
    return redirect(url_for('movimientos'))

@app.route('/entradas_salidas')
def entradas_salidas():
    if 'usuario' not in session:
        flash('Debe iniciar sesión para acceder.')
        return redirect(url_for('login'))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Consulta para calcular las horas trabajadas
    cur.execute("""
        SELECT 
            u.idUsuario,
            u.nombre,
            u.apellido,
            SEC_TO_TIME(SUM(TIMESTAMPDIFF(SECOND, e.hora, s.hora))) AS total_horas
        FROM usuarios u
        JOIN movimientos e ON u.idUsuario = e.idUsuario AND e.tipo = 'Entrada'
        JOIN movimientos s ON u.idUsuario = s.idUsuario 
            AND s.tipo = 'Salida' 
            AND s.fecha = e.fecha 
            AND s.hora > e.hora
        GROUP BY u.idUsuario, u.nombre, u.apellido
        ORDER BY u.apellido, u.nombre
    """)
    
    horas_trabajadas = cur.fetchall()
    cur.close()

    return render_template('entradas_salidas.html', horas_trabajadas=horas_trabajadas)

#Todo el codigo de python va antes de este if
if __name__ == '__main__':
    app.run(port=5500, debug=True)


