import streamlit as st
import sqlite3
import pandas as pd
import io
import requests
from bs4 import BeautifulSoup

st.set_page_config(page_title="مدیریت هوشمند خرید", layout="wide")

STATUS_OPTIONS = ["کالاهای درخواستی", "کالاهای ارسال شده", "کالاهای موجود"]

# ================= سیستم ورود (Login) =================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.title("🔐 ورود به سیستم")
    with st.form("login_form"):
        username = st.text_input("نام کاربری")
        password = st.text_input("رمز عبور", type="password")
        submit = st.form_submit_button("ورود")
        if submit:
            if username == "Admin" and password == "Sw.123456":
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("نام کاربری یا رمز عبور اشتباه است.")
    st.stop()

# ================= دیتابیس و تنظیمات پایدار =================
def init_db():
    conn = sqlite3.connect('smart_excel.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, category TEXT, status TEXT, supplier_link TEXT, digikala_link TEXT, dkp_code TEXT,
        quantity_needed INTEGER, length_cm REAL, width_cm REAL, height_cm REAL, pcs_per_carton INTEGER,
        cbm_rate_toman REAL, buy_price_yuan REAL, digikala_price_toman REAL, tax_amount_toman REAL,
        commission_percent REAL, processing_fee_toman REAL, pure_profit_toman REAL, profit_percent REAL,
        carton_weight_kg REAL, net_sales_toman REAL
    )
    ''')
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN carton_weight_kg REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN net_sales_toman REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value REAL)''')
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('lifetime_yuan', 0.0)")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('lifetime_shipping', 0.0)")
    
    cursor.execute("UPDATE products SET status = 'کالاهای درخواستی' WHERE status = 'جدید' OR status = 'نیاز به شارژ'")
    cursor.execute("UPDATE products SET status = 'کالاهای موجود' WHERE status = 'موجودی کافی'")
    
    conn.commit()
    conn.close()

init_db()

conn = sqlite3.connect('smart_excel.db')
cursor = conn.cursor()
cursor.execute("SELECT value FROM settings WHERE key='yuan_rate'")
row = cursor.fetchone()
saved_yuan = row[0] if row else 9000.0
conn.close()

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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'fa,en-US;q=0.9,en;q=0.8',
            'Referer': 'https://www.google.com/'
        }
        res = requests.get('https://www.tgju.org/profile/price_cny', headers=headers, timeout=8)
        soup = BeautifulSoup(res.text, 'html.parser')
        price_tag = soup.find('span', {'data-col': 'info.last_trade.PDrCotVal'})
        if price_tag:
            price_rial = int(price_tag.text.replace(',', ''))
            return int(price_rial / 10)
    except:
        pass
    return None

with st.sidebar:
    st.header("تنظیمات عمومی")
    
    if st.button("🔄 آپدیت آنلاین قیمت یوان"):
        live_price = get_live_yuan()
        if live_price:
            conn = sqlite3.connect('smart_excel.db')
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('yuan_rate', ?)", (live_price,))
            conn.commit()
            conn.close()
            st.success(f"آپدیت شد: {live_price:,} تومان")
            st.rerun()
        else:
            st.error("خطا در دریافت قیمت. سایت مبدا پاسخگو نیست.")
            
    conn = sqlite3.connect('smart_excel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='yuan_rate'")
    row = cursor.fetchone()
    saved_yuan = row[0] if row else 9000.0
    conn.close()

    yuan_rate = st.number_input("نرخ روز یوان (تومان):", value=int(saved_yuan), step=100)
    if st.button("💾 ذخیره قیمت دستی"):
        conn = sqlite3.connect('smart_excel.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('yuan_rate', ?)", (yuan_rate,))
        conn.commit()
        conn.close()
        st.success("قیمت جدید ثبت شد!")
        st.rerun()

    st.markdown("---")
    st.subheader("تنظیمات آمار")
    if st.button("⚠️ صفر کردن کنتور انباشتی خرید"):
        conn = sqlite3.connect('smart_excel.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value=0 WHERE key='lifetime_yuan'")
        cursor.execute("UPDATE settings SET value=0 WHERE key='lifetime_shipping'")
        conn.commit()
        conn.close()
        st.success("آمار کنتور صفر شد!")
        st.rerun()


# ================= توابع محاسباتی =================
def dynamic_calc(row, current_yuan):
    try:
        length = float(row['length_cm'])
        width = float(row['width_cm'])
        height = float(row['height_cm'])
        pcs = int(row['pcs_per_carton'])
        qty = int(row['quantity_needed'])
        cbm_rate = float(row['cbm_rate_toman'])
        price_yuan = float(row['buy_price_yuan'])
        dk_price = float(row['digikala_price_toman'])
        tax = float(row['tax_amount_toman'])
        comm_pct = float(row['commission_percent'])
        proc_fee = float(row['processing_fee_toman'])
        
        carton_cbm = (length * width * height) / 1000000
        item_cbm = carton_cbm / pcs if pcs > 0 else 0
        item_shipping_toman = item_cbm * cbm_rate
        item_cost_toman = (price_yuan * current_yuan) + item_shipping_toman
        
        item_dk_net = dk_price - tax - (dk_price * (comm_pct / 100)) - proc_fee
        
        item_profit = item_dk_net - item_cost_toman
        total_net_profit = item_profit * qty
        
        profit_margin_pct = (item_profit / dk_price) * 100 if dk_price > 0 else 0
        
        return pd.Series([total_net_profit, profit_margin_pct, item_dk_net])
    except:
        return pd.Series([0.0, 0.0, 0.0])

def render_product_table(df_subset, tab_key):
    if df_subset.empty:
        st.info("لیست کالاها در این بخش خالی است.")
        return
        
    st.info("💡 برای ویرایش اطلاعات، روی سلول‌ها کلیک کنید. در پایان حتماً دکمه ذخیره را بزنید.")
    
    edited_df = st.data_editor(
        df_subset,
        key=f"editor_{tab_key}",
        use_container_width=True,
        hide_index=True,
        column_order=[
            "id", "name", "category", "status", "dkp_code", "quantity_needed",
            "pcs_per_carton", "cbm_per_carton", "cbm_rate_toman", "buy_price_yuan",
            "digikala_price_toman", "commission_percent", "processing_fee_toman",
            "net_sales_toman", "pure_profit_toman", "profit_percent"
        ],
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
            "cbm_rate_toman": st.column_config.NumberColumn("هزینه CBM (تومان)", format="%d"),
            "buy_price_yuan": st.column_config.NumberColumn("قیمت خرید(یوان)"),
            "digikala_price_toman": st.column_config.NumberColumn("قیمت فروش (تومان)", format="%d"),
            "tax_amount_toman": st.column_config.NumberColumn("مالیات (تومان)", format="%d"),
            "commission_percent": st.column_config.NumberColumn("کمیسیون (%)"),
            "processing_fee_toman": st.column_config.NumberColumn("هزینه پردازش (تومان)", format="%d"),
            "net_sales_toman": st.column_config.NumberColumn("خالص فروش هر واحد", disabled=True, format="%d"),
            "pure_profit_toman": st.column_config.NumberColumn("سود خالص کل (تومان)", disabled=True, format="%d"),
            "profit_percent": st.column_config.NumberColumn("حاشیه سود", disabled=True, format="%.2f %%"),
            "cbm_per_carton": st.column_config.NumberColumn("CBM هر کارتن", disabled=True, format="%.4f"),
        }
    )

    # گرفتن آمار کنتور از دیتابیس
    conn = sqlite3.connect('smart_excel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='lifetime_yuan'")
    lt_yuan_row = cursor.fetchone()
    lt_yuan = lt_yuan_row[0] if lt_yuan_row else 0.0
    
    cursor.execute("SELECT value FROM settings WHERE key='lifetime_shipping'")
    lt_shipping_row = cursor.fetchone()
    lt_shipping = lt_shipping_row[0] if lt_shipping_row else 0.0
    conn.close()

    # نمایش کنتور به شکل باکس‌های رنگی
    st.markdown(f"""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 2px solid #dc3545; margin-top: 15px; margin-bottom: 20px; display: flex; justify-content: space-around;'>
        <div style='text-align: center;'>
            <p style='margin: 0; color: #6c757d; font-size: 15px; font-weight: bold;'>مجموع کل خریدهای انباشتی (یوان)</p>
            <h2 style='margin: 5px 0 0 0; color: #0d6efd;'>{lt_yuan:,.0f} ¥</h2>
        </div>
        <div style='text-align: center;'>
            <p style='margin: 0; color: #6c757d; font-size: 15px; font-weight: bold;'>مجموع هزینه‌های انباشتی حمل و ترخیص (تومان)</p>
            <h2 style='margin: 5px 0 0 0; color: #dc3545;'>{lt_shipping:,.0f} ₮</h2>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("💾 ذخیره تغییرات", key=f"save_btn_{tab_key}"):
        conn = sqlite3.connect('smart_excel.db')
        cursor = conn.cursor()
        
        added_lt_yuan = 0.0
        added_lt_shipping = 0.0

        for _, row in edited_df.iterrows():
            orig_row = df_subset[df_subset['id'] == row['id']].iloc[0]
            
            # ثبت در کنتور فقط در صورت تغییر وضعیت از درخواستی به ارسال شده یا موجود
            if orig_row['status'] == 'کالاهای درخواستی' and row['status'] in ['کالاهای ارسال شده', 'کالاهای موجود']:
                added_lt_yuan += float(row['buy_price_yuan'] * row['quantity_needed'])
                cbm = (row['length_cm'] * row['width_cm'] * row['height_cm']) / 1000000
                pcs = row['pcs_per_carton'] if row['pcs_per_carton'] > 0 else 1
                added_lt_shipping += float((cbm / pcs) * row['cbm_rate_toman'] * row['quantity_needed'])

            cursor.execute('''
                UPDATE products SET
                name=?, category=?, status=?, supplier_link=?, digikala_link=?, dkp_code=?,
                quantity_needed=?, length_cm=?, width_cm=?, height_cm=?, pcs_per_carton=?,
                cbm_rate_toman=?, buy_price_yuan=?, digikala_price_toman=?, tax_amount_toman=?,
                commission_percent=?, processing_fee_toman=?, carton_weight_kg=?
                WHERE id=?
            ''', (
                row['name'], row['category'], row['status'], row['supplier_link'], row['digikala_link'], row['dkp_code'],
                row['quantity_needed'], row['length_cm'], row['width_cm'], row['height_cm'], row['pcs_per_carton'],
                row['cbm_rate_toman'], row['buy_price_yuan'], row['digikala_price_toman'], row['tax_amount_toman'],
                row['commission_percent'], row['processing_fee_toman'], row['carton_weight_kg'], row['id']
            ))
            
        # آپدیت مقادیر کنتور در دیتابیس
        if added_lt_yuan > 0 or added_lt_shipping > 0:
            cursor.execute("UPDATE settings SET value = value + ? WHERE key='lifetime_yuan'", (added_lt_yuan,))
            cursor.execute("UPDATE settings SET value = value + ? WHERE key='lifetime_shipping'", (added_lt_shipping,))
            
        conn.commit()
        conn.close()
        st.success("تغییرات با موفقیت ذخیره شد!")
        st.rerun()

    st.markdown("---")
    with st.expander("🗑️ حذف کالا از سیستم"):
        col1, col2 = st.columns([3, 1])
        options = {f"{row['id']} - {row['name']}": row['id'] for _, row in df_subset.iterrows()}
        if options:
            selected_to_delete = col1.selectbox("کالای مورد نظر را برای حذف انتخاب کنید:", list(options.keys()), key=f"del_sel_{tab_key}")
            if col2.button("حذف دائمی", key=f"del_btn_{tab_key}"):
                prod_id = options[selected_to_delete]
                conn = sqlite3.connect('smart_excel.db')
                c = conn.cursor()
                c.execute("DELETE FROM products WHERE id=?", (prod_id,))
                conn.commit()
                conn.close()
                st.success("کالا با موفقیت حذف شد!")
                st.rerun()

# ================= خواندن اطلاعات و تب‌ها =================
tabs = st.tabs(["📋 کل کالاها", "🛒 درخواستی", "✈️ ارسال شده", "📦 موجود", "➕ افزودن جدید", "💡 پیشنهاد خرید", "📥 اکسل"])

conn = sqlite3.connect('smart_excel.db')
df = pd.read_sql_query("SELECT * FROM products", conn)
conn.close()

if not df.empty:
    df[['pure_profit_toman', 'profit_percent', 'net_sales_toman']] = df.apply(lambda r: dynamic_calc(r, yuan_rate), axis=1)
    df['cbm_per_carton'] = (df['length_cm'] * df['width_cm'] * df['height_cm']) / 1000000
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 گزارش مالی (زنده)")
    for status in STATUS_OPTIONS:
        df_status = df[df['status'] == status]
        total_yuan = (df_status['buy_price_yuan'] * df_status['quantity_needed']).sum() if not df_status.empty else 0
        total_profit = df_status['pure_profit_toman'].sum() if not df_status.empty else 0
        total_net_sales = (df_status['net_sales_toman'] * df_status['quantity_needed']).sum() if not df_status.empty else 0
        
        st.sidebar.markdown(f"**{status}**")
        st.sidebar.caption(f"🔹 ارزش: `{total_yuan:,.0f}` یوان")
        st.sidebar.caption(f"🟩 کل خالص فروش: `{total_net_sales:,.0f}` تومان")
        st.sidebar.caption(f"🔸 سود خالص: `{total_profit:,.0f}` تومان")

with tabs[0]: 
    render_product_table(df, "all")
with tabs[1]: 
    if not df.empty:
        render_product_table(df[df['status'] == 'کالاهای درخواستی'], "req")
    else:
        st.info("لیست کالاها در این بخش خالی است.")
with tabs[2]: 
    if not df.empty:
        render_product_table(df[df['status'] == 'کالاهای ارسال شده'], "sent")
    else:
        st.info("لیست کالاها در این بخش خالی است.")
with tabs[3]: 
    if not df.empty:
        render_product_table(df[df['status'] == 'کالاهای موجود'], "stock")
    else:
        st.info("لیست کالاها در این بخش خالی است.")

with tabs[4]:
    with st.form("add_product_form"):
        col1, col2, col3 = st.columns(3)
        name = col1.text_input("نام کالا")
        category = col2.text_input("دسته بندی")
        status = col3.selectbox("وضعیت خرید", STATUS_OPTIONS)
        
        col4, col5, col6 = st.columns(3)
        sup_link = col4.text_input("لینک تامین کننده")
        dk_link = col5.text_input("لینک دیجی کالا")
        dkp = col6.text_input("کد DKP")
        
        col7, col8, col9, col10 = st.columns(4)
        qty = col7.number_input("تعداد نیاز", min_value=1, value=10)
        buy_price = col8.number_input("قیمت خرید (یوان)", min_value=0.0, value=10.0)
        pcs_carton = col9.number_input("تعداد در کارتن", min_value=1, value=50)
        cbm_rate = col10.number_input("هزینه هر CBM (تومان)", min_value=0.0, value=15000000.0)
        
        col11, col12, col13, col_weight = st.columns(4)
        length = col11.number_input("طول (cm)", min_value=0.0, value=50.0)
        width = col12.number_input("عرض (cm)", min_value=0.0, value=40.0)
        height = col13.number_input("ارتفاع (cm)", min_value=0.0, value=30.0)
        weight = col_weight.number_input("وزن کارتن (kg)", min_value=0.0, value=10.0)
        
        col14, col15, col16, col17 = st.columns(4)
        dk_price = col14.number_input("قیمت فروش (تومان)", min_value=0.0, value=200000.0)
        tax = col15.number_input("مالیات (تومان)", min_value=0.0, value=0.0)
        comm = col16.number_input("کمیسیون (%)", min_value=0.0, value=5.0)
        proc_fee = col17.number_input("هزینه پردازش (تومان)", min_value=0.0, value=5000.0)
        
        if st.form_submit_button("ثبت کالا"):
            conn = sqlite3.connect('smart_excel.db')
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO products (name, category, status, supplier_link, digikala_link, dkp_code, quantity_needed, length_cm, width_cm, height_cm, pcs_per_carton, cbm_rate_toman, buy_price_yuan, digikala_price_toman, tax_amount_toman, commission_percent, processing_fee_toman, pure_profit_toman, profit_percent, carton_weight_kg, net_sales_toman) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, 0)''', 
                           (name, category, status, sup_link, dk_link, dkp, qty, length, width, height, pcs_carton, cbm_rate, buy_price, dk_price, tax, comm, proc_fee, weight))
            
            # افزودن به کنتور در صورت ثبت مستقیم کالای ارسال شده یا موجود
            if status in ['کالاهای ارسال شده', 'کالاهای موجود']:
                added_yuan = buy_price * qty
                cbm = (length * width * height) / 1000000
                pcs = pcs_carton if pcs_carton > 0 else 1
                added_shipping = (cbm / pcs) * cbm_rate * qty
                cursor.execute("UPDATE settings SET value = value + ? WHERE key='lifetime_yuan'", (added_yuan,))
                cursor.execute("UPDATE settings SET value = value + ? WHERE key='lifetime_shipping'", (added_shipping,))
                
            conn.commit()
            conn.close()
            st.success("کالا ثبت شد!")
            st.rerun()

with tabs[5]:
    st.subheader("تخصیص هوشمند بودجه (مخصوص کالاهای درخواستی)")
    budget = st.number_input("بودجه (یوان):", min_value=0, value=30000, step=1000)
    
    if not df.empty:
        df_budget = df[df['status'] == 'کالاهای درخواستی'].copy()
        if not df_budget.empty:
            df_budget = df_budget.sort_values(by='profit_percent', ascending=False)
            
            suggested, rem_budget, total_profit = [], budget, 0
            for _, p in df_budget.iterrows():
                cost = p['buy_price_yuan'] * p['quantity_needed']
                if rem_budget >= cost:
                    suggested.append({"نام کالا": p['name'], "تعداد": p['quantity_needed'], "هزینه (یوان)": cost, "درصد سود": f"{p['profit_percent']:.2f}%"})
                    rem_budget -= cost
                    total_profit += p['pure_profit_toman']
                    
            if suggested:
                st.table(pd.DataFrame(suggested))
                st.success(f"باقیمانده بودجه: {rem_budget:,.0f} یوان")
                st.info(f"مجموع سود خالص این خرید: {total_profit:,.0f} تومان")
            else:
                st.warning("با این بودجه پیشنهادی یافت نشد.")
        else:
            st.info("هیچ 'کالای درخواستی' برای محاسبه بودجه وجود ندارد.")
    else:
        st.info("لیست کالاها خالی است.")

with tabs[6]:
    st.subheader("📥 ورودی/خروجی اکسل")
    sample_df = pd.DataFrame({
        'نام کالا': ['نمونه'], 'دسته بندی': ['ورزشی'], 'وضعیت': ['کالاهای درخواستی'], 'لینک تامین': ['https://'], 
        'لینک دیجی': ['https://'], 'کد DKP': [''], 'تعداد': [10], 'قیمت خرید(یوان)': [50], 
        'تعداد در کارتن': [20], 'وزن هر کارتن': [10], 'هزینه CBM': [15000000], 'طول': [40], 'عرض': [30], 'ارتفاع': [20], 
        'قیمت فروش': [500000], 'مالیات': [0], 'کمیسیون(%)': [5], 'هزینه پردازش': [5000]
    })
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        sample_df.to_excel(writer, index=False)
    st.download_button("دانلود اکسل نمونه", data=buffer.getvalue(), file_name="template.xlsx", mime="application/vnd.ms-excel")
    
    st.markdown("---")
    uploaded_file = st.file_uploader("فایل اکسل پر شده را آپلود کن", type=['xlsx'])
    
    if uploaded_file is not None and st.button("ثبت گروهی"):
        try:
            df_in = pd.read_excel(uploaded_file)
            conn = sqlite3.connect('smart_excel.db')
            cursor = conn.cursor()
            
            added_lt_yuan = 0.0
            added_lt_shipping = 0.0
            
            for _, row in df_in.iterrows():
                status_val = str(row.get('وضعیت', 'کالاهای درخواستی'))
                qty_val = int(row.get('تعداد', 0))
                buy_val = float(row.get('قیمت خرید(یوان)', 0))
                l_val = float(row.get('طول', 0))
                w_val = float(row.get('عرض', 0))
                h_val = float(row.get('ارتفاع', 0))
                pcs_val = int(row.get('تعداد در کارتن', 1))
                cbm_rate_val = float(row.get('هزینه CBM', 0))
                
                # محاسبه کنتور برای کالاهایی که با وضعیت ارسال شده یا موجود وارد سیستم میشوند
                if status_val in ['کالاهای ارسال شده', 'کالاهای موجود']:
                    added_lt_yuan += buy_val * qty_val
                    cbm = (l_val * w_val * h_val) / 1000000
                    pcs = pcs_val if pcs_val > 0 else 1
                    added_lt_shipping += (cbm / pcs) * cbm_rate_val * qty_val

                cursor.execute('''INSERT INTO products (name, category, status, supplier_link, digikala_link, dkp_code, quantity_needed, length_cm, width_cm, height_cm, pcs_per_carton, cbm_rate_toman, buy_price_yuan, digikala_price_toman, tax_amount_toman, commission_percent, processing_fee_toman, pure_profit_toman, profit_percent, carton_weight_kg, net_sales_toman) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, 0)''', (
                    str(row.get('نام کالا', '')), str(row.get('دسته بندی', '')), status_val, 
                    str(row.get('لینک تامین', '')), str(row.get('لینک دیجی', '')), str(row.get('کد DKP', '')), 
                    qty_val, l_val, w_val, h_val, 
                    pcs_val, cbm_rate_val, buy_val, 
                    float(row.get('قیمت فروش', 0)), float(row.get('مالیات', 0)), float(row.get('کمیسیون(%)', 0)), float(row.get('هزینه پردازش', 0)), float(row.get('وزن هر کارتن', 0))
                ))
            
            if added_lt_yuan > 0 or added_lt_shipping > 0:
                cursor.execute("UPDATE settings SET value = value + ? WHERE key='lifetime_yuan'", (added_lt_yuan,))
                cursor.execute("UPDATE settings SET value = value + ? WHERE key='lifetime_shipping'", (added_lt_shipping,))
                
            conn.commit()
            conn.close()
            st.success("اکسل با موفقیت وارد شد!")
            st.rerun()
        except:
            st.error("خطا در ساختار فایل.")