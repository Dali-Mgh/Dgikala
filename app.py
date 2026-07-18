import streamlit as st
import pandas as pd
import io
import requests
import json
from bs4 import BeautifulSoup
from google.cloud import firestore
from google.oauth2 import service_account
from streamlit_option_menu import option_menu

st.set_page_config(page_title="مدیریت هوشمند خرید (Firestore)", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* مخفی کردن المان‌های پیش‌فرض استریم‌لیت */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* استایل‌دهی به کادرهای اطلاعاتی */
    .stAlert {
        border-radius: 10px !important;
    }
    
    /* افکت شناور برای دکمه‌ها */
    .stButton > button {
        border-radius: 8px;
        transition: all 0.3s;
        font-weight: bold;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
</style>
""", unsafe_allow_html=True)

DEFAULT_COLUMNS = [
    "id", "name", "category", "status", "dkp_code", "quantity_needed",
    "length_cm", "width_cm", "height_cm", "carton_weight_kg",
    "pcs_per_carton", "cbm_per_carton", "cbm_rate_toman", "item_shipping_toman", "buy_price_yuan",
    "digikala_price_toman", "commission_percent", "processing_fee_toman", "tax_amount_toman",
    "net_sales_toman", "pure_profit_toman", "profit_percent"
]

COLUMNS_MAP = {
    "id": "شناسه", "name": "نام کالا", "category": "دسته بندی", "status": "وضعیت",
    "supplier_link": "لینک تامین", "digikala_link": "لینک دیجی",
    "dkp_code": "کد DKP", "quantity_needed": "تعداد نیاز",
    "length_cm": "طول (cm)", "width_cm": "عرض (cm)", "height_cm": "ارتفاع (cm)",
    "carton_weight_kg": "وزن هر کارتن (kg)",
    "pcs_per_carton": "تعداد در کارتن", "cbm_per_carton": "CBM هر کارتن",
    "cbm_rate_toman": "هزینه CBM (تومان)", "item_shipping_toman": "هزینه حمل واحد",
    "buy_price_yuan": "قیمت خرید(یوان)", "digikala_price_toman": "قیمت فروش (تومان)",
    "commission_percent": "کمیسیون (%)", "processing_fee_toman": "هزینه پردازش",
    "tax_amount_toman": "ارزش افزوده", "net_sales_toman": "خالص فروش هر واحد",
    "pure_profit_toman": "سود خالص کل (تومان)", "profit_percent": "حاشیه سود"
}

STATUS_OPTIONS = ["کالاهای درخواستی", "کالاهای خریداری شده (انبار چین)", "کالاهای ارسال شده", "کالاهای موجود"]
ACTIVE_STATUSES = ["کالاهای خریداری شده (انبار چین)", "کالاهای ارسال شده", "کالاهای موجود"]

@st.cache_resource
def get_db():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        db = firestore.Client(credentials=creds, project=creds_dict["project_id"])
        return db
    except Exception as e:
        st.error(f"خطا در اتصال به دیتابیس Firestore. \n {e}")
        st.stop()

def init_db():
    db = get_db()
    config_ref = db.collection("settings").document("global_config")
    doc = config_ref.get()
    if not doc.exists:
        config_ref.set({
            "yuan_rate": 9000.0,
            "lifetime_yuan": 0.0,
            "lifetime_shipping": 0.0,
            "lifetime_net_sales": 0.0,
            "visible_columns": DEFAULT_COLUMNS
        })

@st.cache_data
def get_settings():
    db = get_db()
    doc = db.collection("settings").document("global_config").get()
    if doc.exists:
        data = doc.to_dict()
        if "visible_columns" not in data:
            data["visible_columns"] = DEFAULT_COLUMNS
        return data
    return {"yuan_rate": 9000.0, "lifetime_yuan": 0.0, "lifetime_shipping": 0.0, "lifetime_net_sales": 0.0, "visible_columns": DEFAULT_COLUMNS}

def save_settings(settings_dict):
    db = get_db()
    db.collection("settings").document("global_config").set(settings_dict)
    get_settings.clear()

@st.cache_data
def get_products():
    db = get_db()
    docs = db.collection("products").stream()
    records = [doc.to_dict() for doc in docs]
    
    headers = ["id", "name", "category", "status", "supplier_link", "digikala_link", "dkp_code", 
               "quantity_needed", "length_cm", "width_cm", "height_cm", "pcs_per_carton", 
               "cbm_rate_toman", "buy_price_yuan", "digikala_price_toman", "tax_amount_toman", 
               "commission_percent", "processing_fee_toman", "pure_profit_toman", "profit_percent", 
               "carton_weight_kg", "net_sales_toman"]
               
    if not records:
        df = pd.DataFrame(columns=headers)
    else:
        df = pd.DataFrame(records)
        for h in headers:
            if h not in df.columns:
                df[h] = ""
    
    num_cols = ["quantity_needed", "length_cm", "width_cm", "height_cm", "pcs_per_carton", 
                "cbm_rate_toman", "buy_price_yuan", "digikala_price_toman", "tax_amount_toman", 
                "commission_percent", "processing_fee_toman", "pure_profit_toman", "profit_percent", 
                "carton_weight_kg", "net_sales_toman"]
                
    str_cols = ["name", "category", "status", "supplier_link", "digikala_link", "dkp_code"]
    
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype('float64')
        
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
            # حذف کردن 0. از انتهای کدهای DKP
            if col == "dkp_code":
                df[col] = df[col].apply(lambda x: str(x)[:-2] if str(x).endswith('.0') else str(x))
                
    return df

def save_products(df):
    db = get_db()
    col_ref = db.collection("products")
    
    docs = col_ref.stream()
    existing_ids = {doc.id for doc in docs}
    df_ids = {str(int(float(x))) for x in df['id'].tolist() if pd.notna(x)}
    
    batch = db.batch()
    for doc_id in (existing_ids - df_ids):
        batch.delete(col_ref.document(doc_id))
        
    for _, row in df.iterrows():
        doc_id = str(int(float(row['id'])))
        doc_ref = col_ref.document(doc_id)
        row_dict = row.fillna("").to_dict()
        
        clean_dict = {}
        for k, v in row_dict.items():
            if hasattr(v, 'item'):
                clean_dict[k] = v.item()
            else:
                clean_dict[k] = v
        batch.set(doc_ref, clean_dict)
        
    batch.commit()
    get_products.clear()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.title("🔐 ورود به سیستم مدیریت خرید")
    with st.form("login_form"):
        username = st.text_input("نام کاربری")
        password = st.text_input("رمز عبور", type="password")
        submit = st.form_submit_button("ورود به داشبورد")
        if submit:
            if username == "Admin" and password == "Sw.123456":
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("نام کاربری یا رمز عبور اشتباه است.")
    st.stop()

if "db_initialized" not in st.session_state:
    init_db()
    st.session_state["db_initialized"] = True

st.markdown("<h1 style='text-align: center; color: #ef394e; padding-bottom: 10px; font-weight: 900;'>نرم افزار سفارشی لوتوس</h1>", unsafe_allow_html=True)

def get_live_yuan():
    try:
        res = requests.get('https://brsapi.ir/FreeTsetmcBourseApi/Api_Free_Gold_Currency_v2.json', timeout=5)
        if res.status_code == 200:
            data = res.json()
            if 'currency' in data:
                for item in data['currency']:
                    if 'یوان' in item.get('name', ''):
                        return int(item['price'] / 10) 
    except:
        pass
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get('https://www.tgju.org/profile/price_cny', headers=headers, timeout=8)
        soup = BeautifulSoup(res.text, 'html.parser')
        price_tag = soup.find('span', {'data-col': 'info.last_trade.PDrCotVal'})
        if price_tag:
            price_rial = int(price_tag.text.replace(',', ''))
            return int(price_rial / 10)
    except:
        pass
    return None

def calculate_fees(dk_price, comm_pct):
    if dk_price <= 0:
        return 0.0, 0.0
    proc_fee = dk_price * 0.07
    proc_fee = max(36000.0, min(proc_fee, 240000.0))
    comm_amount = dk_price * (comm_pct / 100.0)
    tax = (0.10 * (proc_fee / 2.0)) + (0.10 * comm_amount)
    return float(proc_fee), float(tax)

def dynamic_calc(row, current_yuan):
    try:
        length, width, height = float(row['length_cm']), float(row['width_cm']), float(row['height_cm'])
        pcs, qty = int(row['pcs_per_carton']), int(row['quantity_needed'])
        cbm_rate = float(row['cbm_rate_toman'])
        price_yuan, dk_price = float(row['buy_price_yuan']), float(row['digikala_price_toman'])
        comm_pct = float(row['commission_percent'])
        
        proc_fee, tax = calculate_fees(dk_price, comm_pct)
        carton_cbm = (length * width * height) / 1000000
        item_cbm = carton_cbm / pcs if pcs > 0 else 0
        item_shipping_toman = item_cbm * cbm_rate
        item_cost_toman = (price_yuan * current_yuan) + item_shipping_toman
        
        comm_amount = dk_price * (comm_pct / 100.0)
        item_dk_net = dk_price - tax - comm_amount - proc_fee
        item_profit = item_dk_net - item_cost_toman
        total_net_profit = item_profit * qty
        profit_margin_pct = (item_profit / dk_price) * 100 if dk_price > 0 else 0
        
        return pd.Series([total_net_profit, profit_margin_pct, item_dk_net, proc_fee, tax, item_shipping_toman])
    except Exception:
        return pd.Series([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

settings_data = get_settings()
saved_yuan = settings_data.get('yuan_rate', 9000.0)
df = get_products()

if not df.empty:
    df[['pure_profit_toman', 'profit_percent', 'net_sales_toman', 'processing_fee_toman', 'tax_amount_toman', 'item_shipping_toman']] = df.apply(lambda r: dynamic_calc(r, saved_yuan), axis=1, result_type='expand')
    df['cbm_per_carton'] = (pd.to_numeric(df['length_cm']) * pd.to_numeric(df['width_cm']) * pd.to_numeric(df['height_cm'])) / 1000000

with st.sidebar:
    st.header("تنظیمات یوان")
    if st.button("🔄 آپدیت آنلاین قیمت یوان"):
        live_price = get_live_yuan()
        if live_price:
            settings_data['yuan_rate'] = float(live_price)
            save_settings(settings_data)
            st.success(f"آپدیت شد: {live_price:,} تومان")
            st.rerun()
        else:
            st.error("خطا در دریافت قیمت.")
            
    yuan_rate = st.number_input("نرخ روز یوان (تومان):", value=int(saved_yuan), step=100)
    if st.button("💾 ذخیره قیمت دستی"):
        settings_data['yuan_rate'] = float(yuan_rate)
        save_settings(settings_data)
        st.success("قیمت ثبت شد!")
        st.rerun()

    st.markdown("---")
    
    # منوی اصلی برنامه قرار گرفته در سایدبار زیر یوان
    selected_menu = option_menu(
        menu_title="منوی ناوبری",
        options=["کل کالاها", "درخواستی", "انبار چین", "ارسال شده", "موجود", "افزودن جدید", "پیشنهاد خرید", "اکسل", "تجمیعی DKP"],
        icons=["list-ul", "cart", "building", "airplane", "box", "plus-circle", "lightbulb", "file-earmark-excel", "graph-up"],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#fd7e14", "font-size": "18px"},
            "nav-link": {"font-size": "15px", "text-align": "right", "margin":"0px", "--hover-color": "#e9ecef", "color": "#333"},
            "nav-link-selected": {"background-color": "#ef394e", "color": "white"},
        }
    )
    
    st.markdown("---")
    with st.expander("⚙️ تنظیمات ستون‌های جدول"):
        selected_cols = st.multiselect(
            "انتخاب ستون‌ها:",
            options=list(COLUMNS_MAP.keys()),
            format_func=lambda x: COLUMNS_MAP[x],
            default=settings_data.get('visible_columns', DEFAULT_COLUMNS)
        )
        if st.button("💾 ذخیره نمای ستون‌ها"):
            settings_data['visible_columns'] = selected_cols
            save_settings(settings_data)
            st.success("ذخیره شد!")
            st.rerun()

    with st.expander("⚠️ تنظیمات آمار (خطرناک)"):
        if st.button("صفر کردن کنتور انباشتی"):
            settings_data['lifetime_yuan'] = 0.0
            settings_data['lifetime_shipping'] = 0.0
            settings_data['lifetime_net_sales'] = 0.0
            save_settings(settings_data)
            st.success("صفر شد!")
            st.rerun()

    st.markdown("---")
    with st.expander("📊 گزارش مالی (زنده)", expanded=False):
        if not df.empty:
            for status in STATUS_OPTIONS:
                df_status = df[df['status'] == status]
                total_yuan = (pd.to_numeric(df_status['buy_price_yuan']) * pd.to_numeric(df_status['quantity_needed'])).sum() if not df_status.empty else 0
                total_profit = pd.to_numeric(df_status['pure_profit_toman']).sum() if not df_status.empty else 0
                total_net_sales = (pd.to_numeric(df_status['net_sales_toman']) * pd.to_numeric(df_status['quantity_needed'])).sum() if not df_status.empty else 0
                
                st.markdown(f"**{status}**")
                st.caption(f"🔹 ارزش: `{total_yuan:,.0f}` یوان")
                st.caption(f"🟩 کل خالص فروش: `{total_net_sales:,.0f}` تومان")
                st.caption(f"🔸 سود خالص: `{total_profit:,.0f}` تومان")

def render_product_table(df_subset, tab_key):
    if df_subset.empty:
        st.info("لیست کالاها در این بخش خالی است.")
        return
        
    st.info("💡 برای ویرایش اطلاعات، روی سلول‌ها کلیک کنید. ارزش افزوده، هزینه پردازش و هزینه حمل خودکار محاسبه می‌شوند.")
    
    display_df = df_subset.copy()
    display_df['cbm_rate_toman'] = display_df['cbm_rate_toman'].map('{:,.0f}'.format)
    display_df['digikala_price_toman'] = display_df['digikala_price_toman'].map('{:,.0f}'.format)
    display_df['tax_amount_toman'] = display_df['tax_amount_toman'].map('{:,.0f}'.format)
    display_df['processing_fee_toman'] = display_df['processing_fee_toman'].map('{:,.0f}'.format)
    display_df['item_shipping_toman'] = display_df['item_shipping_toman'].map('{:,.0f}'.format)
    display_df['net_sales_toman'] = display_df['net_sales_toman'].map('{:,.0f}'.format)
    display_df['pure_profit_toman'] = display_df['pure_profit_toman'].map('{:,.0f}'.format)
    display_df['profit_percent'] = display_df['profit_percent'].map('{:.2f} %'.format)
    display_df['cbm_per_carton'] = display_df['cbm_per_carton'].map('{:.4f}'.format)

    edited_df = st.data_editor(
        display_df,
        key=f"editor_{tab_key}",
        use_container_width=True,
        hide_index=True,
        column_order=settings_data.get('visible_columns', DEFAULT_COLUMNS),
        column_config={
            "id": st.column_config.NumberColumn("شناسه", disabled=True),
            "name": "نام کالا",
            "category": "دسته بندی",
            "status": st.column_config.SelectboxColumn("وضعیت", options=STATUS_OPTIONS),
            "supplier_link": st.column_config.LinkColumn("لینک تامین", display_text="🔗 سایت"),
            "digikala_link": st.column_config.LinkColumn("لینک دیجی", display_text="🔗 سایت"),
            "dkp_code": "کد DKP",
            "quantity_needed": st.column_config.NumberColumn("تعداد نیاز"),
            "length_cm": st.column_config.NumberColumn("طول (cm)"),
            "width_cm": st.column_config.NumberColumn("عرض (cm)"),
            "height_cm": st.column_config.NumberColumn("ارتفاع (cm)"),
            "carton_weight_kg": st.column_config.NumberColumn("وزن هر کارتن (kg)"),
            "pcs_per_carton": st.column_config.NumberColumn("تعداد در کارتن"),
            "cbm_rate_toman": st.column_config.TextColumn("هزینه CBM (تومان)"),
            "item_shipping_toman": st.column_config.TextColumn("هزینه حمل واحد", disabled=True),
            "buy_price_yuan": st.column_config.NumberColumn("قیمت خرید(یوان)"),
            "digikala_price_toman": st.column_config.TextColumn("قیمت فروش (تومان)"),
            "tax_amount_toman": st.column_config.TextColumn("ارزش افزوده", disabled=True),
            "commission_percent": st.column_config.NumberColumn("کمیسیون (%)"),
            "processing_fee_toman": st.column_config.TextColumn("هزینه پردازش", disabled=True),
            "net_sales_toman": st.column_config.TextColumn("خالص فروش هر واحد", disabled=True),
            "pure_profit_toman": st.column_config.TextColumn("سود خالص کل (تومان)", disabled=True),
            "profit_percent": st.column_config.TextColumn("حاشیه سود", disabled=True),
            "cbm_per_carton": st.column_config.TextColumn("CBM هر کارتن", disabled=True),
        }
    )

    lt_settings = get_settings()
    lt_yuan = lt_settings.get('lifetime_yuan', 0.0)
    lt_shipping = lt_settings.get('lifetime_shipping', 0.0)
    lt_net_sales = lt_settings.get('lifetime_net_sales', 0.0)

    st.markdown(f"""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #dee2e6; margin-top: 15px; margin-bottom: 20px; display: flex; justify-content: space-around; flex-wrap: wrap; gap: 15px;'>
        <div style='text-align: center; flex: 1; min-width: 200px;'>
            <p style='margin: 0; color: #6c757d; font-size: 14px; font-weight: bold;'>مجموع خریدهای انباشتی (یوان)</p>
            <h2 style='margin: 5px 0 0 0; color: #0d6efd;'>{lt_yuan:,.0f} ¥</h2>
        </div>
        <div style='text-align: center; flex: 1; min-width: 200px;'>
            <p style='margin: 0; color: #6c757d; font-size: 14px; font-weight: bold;'>مجموع هزینه‌های حمل (تومان)</p>
            <h2 style='margin: 5px 0 0 0; color: #dc3545;'>{lt_shipping:,.0f} ₮</h2>
        </div>
        <div style='text-align: center; flex: 1; min-width: 200px;'>
            <p style='margin: 0; color: #6c757d; font-size: 14px; font-weight: bold;'>مبلغ خالص فروش کل (تومان)</p>
            <h2 style='margin: 5px 0 0 0; color: #198754;'>{lt_net_sales:,.0f} ₮</h2>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("💾 ذخیره تغییرات", key=f"save_btn_{tab_key}"):
        df_all = get_products()
        df_all = df_all.astype(object)
        added_lt_yuan, added_lt_shipping, added_lt_net_sales = 0.0, 0.0, 0.0

        for _, row in edited_df.iterrows():
            orig_row = df_subset[df_subset['id'] == row['id']].iloc[0]
            cbm_clean = float(str(row['cbm_rate_toman']).replace(',', ''))
            dk_clean = float(str(row['digikala_price_toman']).replace(',', ''))
            comm_val = float(row['commission_percent'])
            
            proc_calc, tax_calc = calculate_fees(dk_clean, comm_val)
            
            if orig_row['status'] not in ACTIVE_STATUSES and row['status'] in ACTIVE_STATUSES:
                added_lt_yuan += float(row['buy_price_yuan'] * row['quantity_needed'])
                cbm = (row['length_cm'] * row['width_cm'] * row['height_cm']) / 1000000
                pcs = row['pcs_per_carton'] if row['pcs_per_carton'] > 0 else 1
                added_lt_shipping += float((cbm / pcs) * cbm_clean * row['quantity_needed'])
                dk_net_single = dk_clean - tax_calc - (dk_clean * (comm_val / 100)) - proc_calc
                added_lt_net_sales += float(dk_net_single * row['quantity_needed'])

            idx = df_all.index[df_all['id'] == row['id']].tolist()
            if idx:
                i = idx[0]
                df_all.loc[i, 'name'] = str(row['name'])
                df_all.loc[i, 'category'] = str(row['category'])
                df_all.loc[i, 'status'] = str(row['status'])
                df_all.loc[i, 'supplier_link'] = str(row['supplier_link'])
                df_all.loc[i, 'digikala_link'] = str(row['digikala_link'])
                df_all.loc[i, 'dkp_code'] = str(row['dkp_code'])
                df_all.loc[i, 'quantity_needed'] = float(row['quantity_needed'])
                df_all.loc[i, 'length_cm'] = float(row['length_cm'])
                df_all.loc[i, 'width_cm'] = float(row['width_cm'])
                df_all.loc[i, 'height_cm'] = float(row['height_cm'])
                df_all.loc[i, 'pcs_per_carton'] = float(row['pcs_per_carton'])
                df_all.loc[i, 'cbm_rate_toman'] = float(cbm_clean)
                df_all.loc[i, 'buy_price_yuan'] = float(row['buy_price_yuan'])
                df_all.loc[i, 'digikala_price_toman'] = float(dk_clean)
                df_all.loc[i, 'tax_amount_toman'] = float(tax_calc)
                df_all.loc[i, 'commission_percent'] = float(comm_val)
                df_all.loc[i, 'processing_fee_toman'] = float(proc_calc)
                df_all.loc[i, 'carton_weight_kg'] = float(row['carton_weight_kg'])
            
        save_products(df_all)
        
        if added_lt_yuan > 0 or added_lt_shipping > 0 or added_lt_net_sales > 0:
            lt_settings = get_settings()
            lt_settings['lifetime_yuan'] = lt_settings.get('lifetime_yuan', 0.0) + added_lt_yuan
            lt_settings['lifetime_shipping'] = lt_settings.get('lifetime_shipping', 0.0) + added_lt_shipping
            lt_settings['lifetime_net_sales'] = lt_settings.get('lifetime_net_sales', 0.0) + added_lt_net_sales
            save_settings(lt_settings)
            
        st.success("تغییرات ذخیره شد!")
        st.rerun()

    with st.expander("🗑️ حذف کالا از سیستم"):
        col1, col2 = st.columns([3, 1])
        options = {f"{row['id']} - {row['name']}": row['id'] for _, row in df_subset.iterrows()}
        if options:
            selected_to_delete = col1.selectbox("انتخاب کالا برای حذف:", list(options.keys()), key=f"del_sel_{tab_key}")
            if col2.button("حذف دائمی", key=f"del_btn_{tab_key}"):
                prod_id = options[selected_to_delete]
                df_all = get_products()
                df_all = df_all[df_all['id'] != prod_id]
                save_products(df_all)
                st.success("کالا حذف شد!")
                st.rerun()

# نوار جستجوی سراسری (فقط در صفحات جداول نمایش داده شود)
if selected_menu in ["کل کالاها", "درخواستی", "انبار چین", "ارسال شده", "موجود"]:
    st.subheader(f"لیست {selected_menu}")
    search_query = st.text_input("🔍 نام کالا یا کد DKP را جستجو کنید:", key=f"search_{selected_menu}")
    
    df_filtered = df
    if search_query:
        df_filtered = df[df['name'].str.contains(search_query, case=False, na=False) | 
                         df['dkp_code'].astype(str).str.contains(search_query, case=False, na=False)]

    if selected_menu == "کل کالاها":
        render_product_table(df_filtered, "all")
    elif selected_menu == "درخواستی":
        render_product_table(df_filtered[df_filtered['status'] == 'کالاهای درخواستی'], "req")
    elif selected_menu == "انبار چین":
        render_product_table(df_filtered[df_filtered['status'] == 'کالاهای خریداری شده (انبار چین)'], "china")
    elif selected_menu == "ارسال شده":
        render_product_table(df_filtered[df_filtered['status'] == 'کالاهای ارسال شده'], "sent")
    elif selected_menu == "موجود":
        render_product_table(df_filtered[df_filtered['status'] == 'کالاهای موجود'], "stock")

if selected_menu == "افزودن جدید":
    st.subheader("➕ ثبت کالای جدید")
    st.info("💡 برای ثبت مجدد کالای تکراری، کد DKP آن را وارد کنید تا اطلاعات به صورت خودکار کپی شود.")
    dkp_to_copy = st.text_input("کد DKP برای کپی اطلاعات (اختیاری):", key="dkp_copy_input")
    
    def_vals = {
        'name': '', 'category': '', 'status': STATUS_OPTIONS[0],
        'supplier_link': '', 'digikala_link': '', 'dkp_code': dkp_to_copy,
        'quantity_needed': 10, 'buy_price_yuan': 10.0, 'pcs_per_carton': 50,
        'cbm_rate_toman': 15000000.0, 'length_cm': 50.0, 'width_cm': 40.0,
        'height_cm': 30.0, 'carton_weight_kg': 10.0, 'digikala_price_toman': 200000.0,
        'commission_percent': 5.0
    }
    
    if dkp_to_copy and not df.empty:
        matched_rows = df[df['dkp_code'].astype(str) == str(dkp_to_copy)]
        if not matched_rows.empty:
            last_record = matched_rows.iloc[-1]
            def_vals.update({
                'name': str(last_record.get('name', '')),
                'category': str(last_record.get('category', '')),
                'supplier_link': str(last_record.get('supplier_link', '')),
                'digikala_link': str(last_record.get('digikala_link', '')),
                'dkp_code': str(last_record.get('dkp_code', '')),
                'buy_price_yuan': float(last_record.get('buy_price_yuan', 10.0)),
                'pcs_per_carton': int(last_record.get('pcs_per_carton', 50)),
                'cbm_rate_toman': float(last_record.get('cbm_rate_toman', 15000000.0)),
                'length_cm': float(last_record.get('length_cm', 50.0)),
                'width_cm': float(last_record.get('width_cm', 40.0)),
                'height_cm': float(last_record.get('height_cm', 30.0)),
                'carton_weight_kg': float(last_record.get('carton_weight_kg', 10.0)),
                'digikala_price_toman': float(last_record.get('digikala_price_toman', 200000.0)),
                'commission_percent': float(last_record.get('commission_percent', 5.0))
            })
            st.success(f"✅ اطلاعات «{def_vals['name']}» بارگذاری شد!")
        else:
            st.warning("کالایی با این کد DKP یافت نشد.")

    with st.form("add_product_form"):
        col1, col2, col3 = st.columns(3)
        name = col1.text_input("نام کالا", value=def_vals['name'])
        category = col2.text_input("دسته بندی", value=def_vals['category'])
        status = col3.selectbox("وضعیت خرید", STATUS_OPTIONS)
        
        col4, col5, col6 = st.columns(3)
        sup_link = col4.text_input("لینک تامین کننده", value=def_vals['supplier_link'])
        dk_link = col5.text_input("لینک دیجی کالا", value=def_vals['digikala_link'])
        dkp = col6.text_input("کد DKP", value=def_vals['dkp_code'])
        
        col7, col8, col9, col10 = st.columns(4)
        qty = col7.number_input("تعداد نیاز", min_value=1, value=int(def_vals['quantity_needed']))
        buy_price = col8.number_input("قیمت خرید (یوان)", min_value=0.0, value=float(def_vals['buy_price_yuan']))
        pcs_carton = col9.number_input("تعداد در کارتن", min_value=1, value=int(def_vals['pcs_per_carton']))
        cbm_rate = col10.number_input("هزینه هر CBM (تومان)", min_value=0.0, value=float(def_vals['cbm_rate_toman']))
        
        col11, col12, col13, col_weight = st.columns(4)
        length = col11.number_input("طول (cm)", min_value=0.0, value=float(def_vals['length_cm']))
        width = col12.number_input("عرض (cm)", min_value=0.0, value=float(def_vals['width_cm']))
        height = col13.number_input("ارتفاع (cm)", min_value=0.0, value=float(def_vals['height_cm']))
        weight = col_weight.number_input("وزن کارتن (kg)", min_value=0.0, value=float(def_vals['carton_weight_kg']))
        
        col14, col15 = st.columns(2)
        dk_price = col14.number_input("قیمت فروش (تومان)", min_value=0.0, value=float(def_vals['digikala_price_toman']))
        comm = col15.number_input("کمیسیون (%)", min_value=0.0, value=float(def_vals['commission_percent']))
        
        if st.form_submit_button("ثبت کالا"):
            df_all = get_products()
            current_max_id = int(pd.to_numeric(df_all['id'], errors='coerce').dropna().max()) if not df_all.empty and 'id' in df_all.columns else 0
            new_id = current_max_id + 1
            
            clean_dkp = str(dkp)[:-2] if str(dkp).endswith('.0') else str(dkp)
            proc_calc, tax_calc = calculate_fees(dk_price, comm)
            
            new_row = {
                'id': new_id, 'name': name, 'category': category, 'status': status, 
                'supplier_link': sup_link, 'digikala_link': dk_link, 'dkp_code': clean_dkp, 
                'quantity_needed': float(qty), 'length_cm': float(length), 'width_cm': float(width), 'height_cm': float(height), 
                'pcs_per_carton': float(pcs_carton), 'cbm_rate_toman': float(cbm_rate), 'buy_price_yuan': float(buy_price), 
                'digikala_price_toman': float(dk_price), 'tax_amount_toman': float(tax_calc), 'commission_percent': float(comm), 
                'processing_fee_toman': float(proc_calc), 'pure_profit_toman': 0.0, 'profit_percent': 0.0, 
                'carton_weight_kg': float(weight), 'net_sales_toman': 0.0
            }
            
            df_all = pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True)
            save_products(df_all)
            
            if status in ACTIVE_STATUSES:
                lt_settings = get_settings()
                lt_settings['lifetime_yuan'] = lt_settings.get('lifetime_yuan', 0.0) + (buy_price * qty)
                cbm = (length * width * height) / 1000000
                lt_settings['lifetime_shipping'] = lt_settings.get('lifetime_shipping', 0.0) + ((cbm / (pcs_carton if pcs_carton>0 else 1)) * cbm_rate * qty)
                lt_settings['lifetime_net_sales'] = lt_settings.get('lifetime_net_sales', 0.0) + ((dk_price - tax_calc - (dk_price * (comm / 100)) - proc_calc) * qty)
                save_settings(lt_settings)
                
            st.success("کالا با موفقیت ثبت شد!")
            st.rerun()

if selected_menu == "پیشنهاد خرید":
    st.subheader("💡 تخصیص هوشمند بودجه (مخصوص کالاهای درخواستی)")
    budget = st.number_input("بودجه خود را وارد کنید (یوان):", min_value=0, value=30000, step=1000)
    
    if not df.empty:
        df_budget = df[df['status'] == 'کالاهای درخواستی'].copy()
        if not df_budget.empty:
            df_budget = df_budget.sort_values(by='profit_percent', ascending=False)
            suggested = []
            rem_budget = budget
            
            for _, p in df_budget.iterrows():
                buy_price = float(p['buy_price_yuan'])
                qty_needed = float(p['quantity_needed'])
                cost_full = buy_price * qty_needed
                
                if cost_full <= 5000:
                    if rem_budget >= cost_full:
                        rem_budget -= cost_full
                        suggested.append((p, qty_needed))
                elif cost_full <= 10000:
                    if qty_needed < 100 and rem_budget >= cost_full:
                        rem_budget -= cost_full
                        suggested.append((p, qty_needed))
                    else:
                        max_qty = int(rem_budget // buy_price)
                        s_qty = min(qty_needed, max_qty)
                        if s_qty > 0:
                            rem_budget -= (s_qty * buy_price)
                            suggested.append((p, s_qty))
                else:
                    max_qty = int(rem_budget // buy_price)
                    s_qty = min(qty_needed, max_qty)
                    if s_qty > 0:
                        rem_budget -= (s_qty * buy_price)
                        suggested.append((p, s_qty))
            
            if suggested:
                st.write("---")
                st.success("✅ سبد خرید پیشنهادی بر اساس بالاترین حاشیه سود آماده شد:")
                
                # --- نمایش جدول کالاهای پیشنهاد شده ---
                suggested_data = []
                for p, s_qty in suggested:
                    suggested_data.append({
                        "کد DKP": p['dkp_code'],
                        "نام کالا": p['name'],
                        "تعداد پیشنهادی": s_qty,
                        "قیمت خرید واحد (یوان)": p['buy_price_yuan'],
                        "جمع یوان": s_qty * p['buy_price_yuan']
                    })
                st.dataframe(pd.DataFrame(suggested_data), use_container_width=True, hide_index=True)
                
                # --- آمار پایین لیست ---
                total_yuan = sum([s_qty * p['buy_price_yuan'] for p, s_qty in suggested])
                total_items = sum([s_qty for p, s_qty in suggested])
                remaining_budget = budget - total_yuan
                
                st.markdown(f"""
                <div style='background-color: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #dee2e6; margin-top: 15px;'>
                    <h4 style='color: #0d6efd; margin-top: 0;'>📊 آمار نهایی سبد پیشنهادی</h4>
                    <p style='margin-bottom: 5px; font-size: 15px;'><b>بودجه اولیه تعیین شده:</b> {budget:,.0f} یوان</p>
                    <p style='margin-bottom: 5px; color: #198754; font-size: 16px;'><b>کل بودجه مصرف شده:</b> {total_yuan:,.0f} یوان</p>
                    <p style='margin-bottom: 5px; color: #dc3545; font-size: 15px;'><b>بودجه باقیمانده:</b> {remaining_budget:,.0f} یوان</p>
                    <p style='margin-bottom: 0; font-size: 15px;'><b>تعداد کل اقلام پیشنهادی:</b> {total_items:,.0f} عدد</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("با این بودجه پیشنهادی یافت نشد.")
        else:
            st.info("هیچ 'کالای درخواستی' برای محاسبه بودجه وجود ندارد.")
    else:
        st.info("لیست کالاها خالی است.")

if selected_menu == "اکسل":
    st.subheader("📥 ورود گروهی اطلاعات از طریق اکسل")
    sample_df = pd.DataFrame({
        'نام کالا': ['نمونه'], 'دسته بندی': ['ورزشی'], 'وضعیت': ['کالاهای درخواستی'], 'لینک تامین': ['https://'], 
        'لینک دیجی': ['https://'], 'کد DKP': [''], 'تعداد': [10], 'قیمت خرید(یوان)': [50], 
        'تعداد در کارتن': [20], 'وزن هر کارتن': [10], 'هزینه CBM': [15000000], 'طول': [40], 'عرض': [30], 'ارتفاع': [20], 
        'قیمت فروش': [500000], 'کمیسیون(%)': [5]
    })
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        sample_df.to_excel(writer, index=False)
    st.download_button("دانلود قالب استاندارد اکسل", data=buffer.getvalue(), file_name="template.xlsx", mime="application/vnd.ms-excel")
    
    st.markdown("---")
    uploaded_file = st.file_uploader("فایل اکسل پر شده را آپلود کنید", type=['xlsx'])
    
    if uploaded_file is not None and st.button("ثبت گروهی کالاها"):
        try:
            df_in = pd.read_excel(uploaded_file)
            df_all = get_products()
            
            added_lt_yuan, added_lt_shipping, added_lt_net_sales = 0.0, 0.0, 0.0
            new_rows = []
            current_max_id = int(pd.to_numeric(df_all['id'], errors='coerce').dropna().max()) if not df_all.empty and 'id' in df_all.columns else 0
            
            for _, row in df_in.iterrows():
                status_val = str(row.get('وضعیت', 'کالاهای درخواستی'))
                qty_val = float(row.get('تعداد', 0))
                buy_val = float(row.get('قیمت خرید(یوان)', 0))
                l_val, w_val, h_val = float(row.get('طول', 0)), float(row.get('عرض', 0)), float(row.get('ارتفاع', 0))
                pcs_val = float(row.get('تعداد در کارتن', 1))
                cbm_rate_val = float(row.get('هزینه CBM', 0))
                dk_price = float(row.get('قیمت فروش', 0))
                comm = float(row.get('کمیسیون(%)', 0))
                
                raw_dkp = str(row.get('کد DKP', ''))
                clean_dkp = raw_dkp[:-2] if raw_dkp.endswith('.0') else raw_dkp
                proc_calc, tax_calc = calculate_fees(dk_price, comm)
                
                if status_val in ACTIVE_STATUSES:
                    added_lt_yuan += buy_val * qty_val
                    cbm = (l_val * w_val * h_val) / 1000000
                    added_lt_shipping += (cbm / (pcs_val if pcs_val > 0 else 1)) * cbm_rate_val * qty_val
                    added_lt_net_sales += (dk_price - tax_calc - (dk_price * (comm / 100)) - proc_calc) * qty_val

                current_max_id += 1
                new_rows.append({
                    'id': current_max_id, 'name': str(row.get('نام کالا', '')), 'category': str(row.get('دسته بندی', '')),
                    'status': status_val, 'supplier_link': str(row.get('لینک تامین', '')), 'digikala_link': str(row.get('لینک دیجی', '')),
                    'dkp_code': clean_dkp, 'quantity_needed': qty_val, 'length_cm': l_val, 'width_cm': w_val, 'height_cm': h_val,
                    'pcs_per_carton': pcs_val, 'cbm_rate_toman': cbm_rate_val, 'buy_price_yuan': buy_val,
                    'digikala_price_toman': dk_price, 'tax_amount_toman': tax_calc, 'commission_percent': comm,
                    'processing_fee_toman': proc_calc, 'pure_profit_toman': 0.0, 'profit_percent': 0.0,
                    'carton_weight_kg': float(row.get('وزن هر کارتن', 0)), 'net_sales_toman': 0.0
                })
            
            if new_rows:
                df_all = pd.concat([df_all, pd.DataFrame(new_rows)], ignore_index=True)
                save_products(df_all)
            
            if added_lt_yuan > 0 or added_lt_shipping > 0 or added_lt_net_sales > 0:
                lt_settings = get_settings()
                lt_settings['lifetime_yuan'] = lt_settings.get('lifetime_yuan', 0.0) + added_lt_yuan
                lt_settings['lifetime_shipping'] = lt_settings.get('lifetime_shipping', 0.0) + added_lt_shipping
                lt_settings['lifetime_net_sales'] = lt_settings.get('lifetime_net_sales', 0.0) + added_lt_net_sales
                save_settings(lt_settings)
                
            st.success("اکسل با موفقیت وارد شد!")
            st.rerun()
        except Exception as e:
            st.error(f"خطا در ساختار فایل: {e}")

if selected_menu == "تجمیعی DKP":
    st.subheader("📈 آمار تجمیعی خرید کالاها بر اساس DKP")
    st.info("این بخش مجموع خریدهای قطعی (انبار چین به بعد) هر کالا را نشان می‌دهد. کالاهای درخواستی در این آمار لحاظ نمی‌شوند.")
    
    if not df.empty:
        # فیلتر برای کالاهایی که DKP دارند و وضعیتشان خریده شده است
        df_valid_dkp = df[(df['dkp_code'].astype(str).str.strip() != '') & (df['status'].isin(ACTIVE_STATUSES))]
        
        if not df_valid_dkp.empty:
            grouped = df_valid_dkp.groupby('dkp_code').agg(
                name=('name', 'first'),
                total_qty=('quantity_needed', 'sum'),
                order_count=('id', 'count')
            ).reset_index()

            grouped = grouped.sort_values(by='total_qty', ascending=False)
            grouped = grouped.rename(columns={
                'dkp_code': 'کد DKP',
                'name': 'نام کالا',
                'total_qty': 'مجموع تعداد خریداری شده (انباشتی)',
                'order_count': 'تعداد محموله‌های ثبت شده'
            })
            
            st.dataframe(grouped, use_container_width=True, hide_index=True)
        else:
            st.info("هیچ کالای خریداری شده‌ای که دارای کد DKP باشد در سیستم ثبت نشده است.")
    else:
        st.info("لیست کالاها خالی است.")

# فوتر اختصاصی در پایین‌ترین بخش برنامه
st.markdown("""
<br><br><br>
<div style='text-align: center; color: #888; font-size: 13px; border-top: 1px solid #eaeaea; padding-top: 15px; margin-top: 50px;'>
    تمامی حقوق این نرم افزار برای <b>آقای محمد قندالی</b> است ©
</div>
""", unsafe_allow_html=True)