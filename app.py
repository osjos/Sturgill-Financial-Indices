from flask import Flask, render_template, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import os  # For checking and managing the cached file

# Initialize Flask app
app = Flask(__name__)

# Firebase initialization
if not firebase_admin._apps:
    cred = credentials.Certificate(r"C:\Users\Pins Collective\btc_mag7_webservice\firebase-key.json")
    firebase_admin.initialize_app(cred)
    print("Firebase initialized successfully!")

# Firestore client
db = firestore.client()

# Path to the cache file
CACHE_FILE = "cached_data.csv"

@app.route('/')
def index():
    """Render the main page with the chart."""
    return render_template('index.html')

@app.route('/chart-data')
def get_chart_data():
    """Fetch data from cache or Firestore and return it as JSON for the normalized BTC/Mag7 index chart."""
    try:
        if os.path.exists(CACHE_FILE):
            df = pd.read_csv(CACHE_FILE)
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
        else:
            # Fetch raw data from Firestore
            collection_ref = db.collection("Indices").document("BTC_Mag7_Index").collection("DailyData")
            docs = collection_ref.stream()

            data = []
            for doc in docs:
                doc_data = doc.to_dict()
                data.append(doc_data)

            df = pd.DataFrame(data)
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)

            valid_start_date = df[['BTC-USD', 'TSLA']].dropna().index.min()
            df = df[df.index >= valid_start_date]
            df.fillna(method='ffill', inplace=True)
            df.to_csv(CACHE_FILE)

        # Normalize prices to start at 100
        normalized_data = df / df.iloc[0] * 100

        # Apply weights
        weights = {
            'BTC-USD': 0.5,
            'MSFT': 0.1,
            'AAPL': 0.1,
            'GOOGL': 0.1,
            'AMZN': 0.1,
            'META': 0.05,
            'NVDA': 0.05
        }
        df['BTC_Mag7_Index'] = (normalized_data * pd.Series(weights)).sum(axis=1)

        # Smooth the index with a 7-day moving average
        df['Smoothed_Index'] = df['BTC_Mag7_Index'].rolling(window=7).mean()

        # Calculate multiple MAs
        df['MA200'] = df['Smoothed_Index'].rolling(window=200).mean()
        df['MA150'] = df['Smoothed_Index'].rolling(window=150).mean()
        df['MA100'] = df['Smoothed_Index'].rolling(window=100).mean()


        # Drop rows with NaN in critical columns
        df.dropna(subset=['Smoothed_Index'], inplace=True)

        # Create response dictionary with all MAs
        response = {
            'dates': df.index.strftime('%Y-%m-%d').tolist(),
            'index_values': [None if pd.isna(x) else x for x in df['Smoothed_Index']],
            'ma200': [None if pd.isna(x) else x for x in df['MA200']],
            'ma150': [None if pd.isna(x) else x for x in df['MA150']],
            'ma100': [None if pd.isna(x) else x for x in df['MA100']],

        }

        # Add cycle tops and bottoms
        cycle_tops = ['2017-12-17', '2021-11-10']
        cycle_bottoms = ['2018-12-15', '2022-06-18']

        response['tops'] = [
            {'date': top, 'value': df.loc[top, 'BTC_Mag7_Index']}
            for top in cycle_tops if top in df.index
        ]
        response['bottoms'] = [
            {'date': bottom, 'value': df.loc[bottom, 'BTC_Mag7_Index']}
            for bottom in cycle_bottoms if bottom in df.index
        ]
        return jsonify(response)

    except Exception as e:
        print("Error in /chart-data:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
