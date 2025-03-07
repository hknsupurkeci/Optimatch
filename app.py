import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
import os
import zipfile
from werkzeug.utils import secure_filename
from services.candidate_service import CandidateService
from services.logging_service import LoggingService
import msal  # Microsoft Authentication Library for Python
from functools import wraps  # For the login_required decorator
import config  # Contains CLIENT_ID, CLIENT_SECRET, and AUTHORITY
import uuid  # For generating unique IDs
import pickle  # For saving data to files

app = Flask(__name__, static_url_path='/static', static_folder='static')
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.secret_key = secrets.token_hex(16)  # 16-byte random secret key

candidate_service = CandidateService()
logging_service = LoggingService()

# Azure AD configuration
CLIENT_ID = config.CLIENT_ID
CLIENT_SECRET = config.CLIENT_SECRET
AUTHORITY = config.AUTHORITY
REDIRECT_PATH = '/getAToken'  # Must match the redirect URI in your Azure AD app registration
SCOPE = ['User.Read']  # To get basic user info
ALLOWED_USERS = config.ALLOWED_USERS  # Add allowed users here

# MSAL app
msal_app = msal.ConfidentialClientApplication(
    CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
)

# Decorator to check if the user is logged in
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        elif session['user'].get('preferred_username') not in ALLOWED_USERS:
            return "Erişim izniniz yok", 403
        return f(*args, **kwargs)
    return decorated_function

# Login route
@app.route('/login')
def login():
    session.clear()
    auth_url = msal_app.get_authorization_request_url(
        SCOPE,
        redirect_uri=url_for('authorized', _external=True)
    )
    return redirect(auth_url)

# Authorization callback route
@app.route(REDIRECT_PATH)
def authorized():
    if request.args.get('code'):
        result = msal_app.acquire_token_by_authorization_code(
            request.args['code'],
            scopes=SCOPE,
            redirect_uri=url_for('authorized', _external=True)
        )
        if 'error' in result:
            return "Hata: {}".format(result.get('error_description'))
        session['user'] = result.get('id_token_claims')
    return redirect(url_for('index'))

# Logout route
@app.route('/logout')
def logout():
    session.clear()
    return redirect(
        'https://login.microsoftonline.com/common/oauth2/v2.0/logout' +
        '?post_logout_redirect_uri=' + url_for('index', _external=True)
    )

# Home page
@app.route('/', methods=['GET'])
@login_required
def index():
    user = session['user']
    # Kullanıcı e-posta adresine göre klasör yolunu oluşturun
    user_folder = os.path.join('uploads', user['preferred_username'])
    # Bu fonksiyonla klasör/dizin ağacını alın
    folder_tree = get_directory_tree(user_folder)
    
    # Artık render_template içinde folder_tree'yi de veriyoruz
    return render_template('index.html', user=user, folder_tree=folder_tree)


# File upload and processing
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('Dosya seçilmedi')
        return redirect(request.url)

    files = request.files.getlist('file')
    job_info = request.form['job_info']
    keywords = request.form['keywords'].split(",")
    candidate_count = int(request.form['candidate_count'])

    # Kullanıcı bilgilerini session'dan alın
    user = session['user']

    # Generate a unique process ID
    process_id = str(uuid.uuid4())

    # Process candidates
    result, valid_candidates = candidate_service.process_candidates(
        files, job_info, keywords, candidate_count, user
    )

    # Save process data on the server side
    process_data = {
        'result': result,
        'valid_candidates': valid_candidates,
        'user_file_path': candidate_service.user_file_path  # Save user file path
    }

    # Save process data to a file
    os.makedirs('process_data', exist_ok=True)
    with open(f'process_data/{process_id}.pkl', 'wb') as f:
        pickle.dump(process_data, f)

    # Store process_id in session
    session['process_id'] = process_id

    # Implementing POST-Redirect-GET pattern
    return redirect(url_for('result'))

# Display results
@app.route('/result', methods=['GET'])
@login_required
def result():
    # Get process_id from session
    process_id = session.get('process_id')

    # If process_id not in session, redirect to home page
    if not process_id:
        return redirect(url_for('index'))

    # Load process data from file
    try:
        with open(f'process_data/{process_id}.pkl', 'rb') as f:
            process_data = pickle.load(f)
    except FileNotFoundError:
        flash('İşlem verileri bulunamadı.')
        return redirect(url_for('index'))

    result = process_data['result']
    valid_candidates = process_data['valid_candidates']

    # Render the result page
    return render_template('result.html', result=result, pdf_files=valid_candidates, user=session['user'])

# Download selected PDFs
@app.route('/download_selected_pdfs', methods=['POST'])
@login_required
def download_selected_pdfs():
    # Session'dan process_id'yi alıyoruz
    process_id = session.get('process_id')

    if not process_id:
        flash("İşlem verileri bulunamadı.")
        return redirect(url_for('index'))

    # İşlem verilerini dosyadan yüklüyoruz
    try:
        with open(f'process_data/{process_id}.pkl', 'rb') as f:
            process_data = pickle.load(f)
    except FileNotFoundError:
        flash('İşlem verileri bulunamadı.')
        return redirect(url_for('index'))

    user_file_path = process_data['user_file_path']

    # candidate_service.user_file_path değerini ayarlıyoruz
    candidate_service.user_file_path = user_file_path

    # Zip dosyasını oluşturuyoruz (parametre olmadan)
    zip_file = candidate_service.zip_selected_pdfs()

    # İşlem verilerini ve process_id'yi temizliyoruz
    session.pop('process_id', None)
    os.remove(f'process_data/{process_id}.pkl')

    # Zip dosyasını kullanıcıya sunuyoruz
    return send_file(zip_file, as_attachment=True)


@app.route('/browse')
def browse():
    # Oturumdaki kullanıcı bilgisini alalım
    if 'user' not in session:
        return redirect(url_for('login'))  # Girişe yönlendirme

    user = session['user']
    user_folder = os.path.join('uploads', user['preferred_username'])

    # Kullanıcıya ait uploads/<mail> klasörümüz var mı?
    if not os.path.exists(user_folder):
        # yoksa oluşturabilir veya hata dönebilirsiniz.
        os.makedirs(user_folder, exist_ok=True)

    # Klasör yapısını çekelim
    folder_tree = get_directory_tree(user_folder)

    # HTML template'e gönderelim
    return render_template('browse.html', folder_tree=folder_tree)

@app.route('/download')
def download_file():
    # İndirilmek istenen dosyanın tam yolu query param'dan geliyor olsun
    file_path = request.args.get('path', None)

    if not file_path or not os.path.exists(file_path):
        return "Dosya bulunamadı veya path parametresi hatalı", 404

    # Güvenlik için kontrol: İstenen dosya, kullanıcının kendi klasörünün altında mı?
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))
    user_root = os.path.join('uploads', user['preferred_username'])

    # `os.path.commonpath` vs. ile user_folder'ı aşıp aşmadığına bakılabilir
    if os.path.commonpath([user_root, file_path]) != user_root:
        return "Başka kullanıcı klasörüne erişim yetkiniz yok!", 403

    # Dosyayı gönder
    return send_file(file_path, as_attachment=True)


def get_directory_tree(root_path):
    """
    Belirtilen klasördeki (root_path) klasör/dosya yapısını
    ağaç şeklinde (dict) döndürür.
    """
    tree = {
        'name': os.path.basename(root_path),
        'path': root_path,
        'type': 'directory',
        'children': []
    }

    try:
        entries = os.listdir(root_path)
    except PermissionError:
        return tree  # izin yoksa boş dön

    for entry in entries:
        full_path = os.path.join(root_path, entry)
        if os.path.isdir(full_path):
            # klasör ise
            tree['children'].append(get_directory_tree(full_path))
        else:
            # dosya ise
            tree['children'].append({
                'name': entry,
                'path': full_path,
                'type': 'file'
            })

    return tree


if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    if not os.path.exists('process_data'):
        os.makedirs('process_data')
    app.run(host=config.HOST, port=config.PORT)