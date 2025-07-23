from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import jwt
from datetime import datetime,timedelta
import os
from dotenv import load_dotenv
from bson.objectid import ObjectId
from flask_jwt_extended import jwt_required, get_jwt_identity,JWTManager,create_access_token
# Load environment variables
load_dotenv()

frontend=os.getenv("FRONTEND")
app = Flask(__name__)
CORS(app, origins=frontend, supports_credentials=True)





#JWT VERIFICATION
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

app.config['JWT_TOKEN_LOCATION'] = ['headers'] 
app.config['JWT_HEADER_NAME'] = 'Authorization'
app.config['JWT_HEADER_TYPE'] = 'Bearer'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)
 # ✅ REQUIRED
jwt = JWTManager(app)

 # Allow all origins for now

# app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
mongo_client = MongoClient(os.getenv("DATABASE"))
db = mongo_client["NITWSE"]

users = db["userdata"]
stocks =db["stocks"]
news=db["news"]
@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response
#LOGIN
def login_validation(email,password):
    email=email.lower();
    temp=users.find_one({"email":email})
    
    if  not temp:
        return "doesntExist"    
    
    if temp["password"]==password:
        return "success"
    else: 
        return "IncorrectPassword"
    
#SIGNUP
def signup_validation(name, email, password, clubs):
    email = email.lower()
    existing_user = users.find_one({"email": email})
    if existing_user:
        return "accountExists"

    new_user = {
        "userID": email.split('@')[0],
        "name": name,
        "email": email,
        "password": password,  # ✔️ left as plain text as per your request
        "active": True,
        "balance": 10000,
        "stockOwned": {},  # changed from list to dict for consistency
        "clubs": clubs,
        "portfolio": 0,
        "transactionHistory": [
            f"Account Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ]
    }

    result = users.insert_one(new_user)
    if result.acknowledged:
        return "success"
    else:
        return "error"

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get("email").lower()
    password = data.get("password")

    result = login_validation(email, password)

    if result == "doesntExist":
        return jsonify({"message": "doesntExist"}), 401
    elif result == "IncorrectPassword":
        return jsonify({"message": "IncorrectPassword"}), 401
    elif result == "success":
        user = users.find_one({"email": email})

        # Create JWT payload
    

       
        token = create_access_token(identity=email, additional_claims={"name": user["name"]})


        # Return token + minimal user info
        return jsonify({
            "message": "success",
            "token": token,
            "user": {
                "name": user["name"],
                "email": user["email"],
                "userID": user["userID"]
            }
        }), 200

    else:
        return jsonify({"message": "Unknown error"}), 500


@app.route('/signup',methods=['POST'])
def signup():
    data=request.get_json()
    name=data.get("name")
    password=data.get("password")
    email=data.get("email")
    
    clubs=data.get("clubs")
    result = signup_validation(name,email,password,clubs)

    if result == "success":
        token = create_access_token(identity=email)
        return jsonify({
            "message": "success",
            "token": token
        }), 200
    else:
        return jsonify({"message": result}), 400




@app.route('/load', methods=['GET'])
@jwt_required()
def load():
    email = get_jwt_identity()

    temp = users.find_one({"email": email})
    if temp:
        temp["_id"] = str(temp["_id"])  # Convert ObjectId to string
        temp.pop("password", None)      # Do NOT send password to frontend
        return jsonify(temp), 200
    else:
        return jsonify({"message": "User not found"}), 404


@app.route('/stocks', methods=['GET'])  # <-- Allow GET
def get_stocks():
    stockList = list(stocks.find())
    for stock in stockList:
        stock["_id"] = str(stock["_id"])  # convert ObjectId to string
    return jsonify(stockList)  # return list directly

@app.route('/news', methods=['GET'])  # <-- Allow GET
def get_news():
    newsList = list(news.find())
    for article in newsList:
        article["_id"] = str(article["_id"])  # convert ObjectId to string

        # ✅ Rename commentArray → comments for frontend
        if "commentArray" in article:
            article["comments"] = article.pop("commentArray")

    return jsonify(newsList)
# return list directly



@app.route('/buy', methods=['POST'])
@jwt_required()
def buy_stock():
    data = request.get_json()
    email = get_jwt_identity()
    UID = data.get('UID')

    stock = stocks.find_one({"UID": UID})
    user = users.find_one({"email": email})

    if not stock or not user:
        return jsonify(success=False, message="Invalid user or stock."), 400

    if not stock.get("IsActive", True) or not user.get("active", True):
        return jsonify(success=False, message="Inactive stock or user."), 400

    if stock["Quantity"] <= 0:
        return jsonify(success=False, message="Stock not available."), 400

    if user["balance"] < stock["Price"]:
        return jsonify(success=False, message="Insufficient balance."), 400

    # Update stock
    stocks.update_one({"UID": UID}, {
        "$inc": {
            "StocksSold":1,
            "BuyNo": 1,
            "Quantity": -1
            
        }
    })

    # Update user: Balance, stockOwned, transactionHistory
    users.update_one({"email": email}, {
        "$inc": {
            "balance": -stock["Price"],
            f"stockOwned.{UID}": 1,
            "portfolio":stock["Price"]
        },
        "$push": {
            "transactionHistory": f"Bought {stock['Name']} at price {stock['Price']} on {datetime.utcnow().isoformat()}"
        }
    })

    return jsonify(success=True, message="Stock bought successfully.")


@app.route('/sell', methods=['POST'])
@jwt_required()
def sell_stock():
    data = request.get_json()
    email = get_jwt_identity()
    UID = data.get('UID')

    stock = stocks.find_one({"UID": UID})
    user = users.find_one({"email": email})

    if not stock or not user:
        return jsonify(success=False, message="Invalid user or stock."), 400

    if not stock.get("IsActive", True) or not user.get("active", True):
        return jsonify(success=False, message="Inactive stock or user."), 400

    owned_qty = user.get("stockOwned", {}).get(UID, 0)
    if owned_qty <= -10 or stock['StocksSold'] < 0:
        return jsonify(success=False, message="Short limit reached."), 400

    # Update stock
    stocks.update_one({"UID": UID}, {
        "$inc": {
            "StocksSold":-1,
            "SellNo": 1,
            "Quantity": 1
        }
    })

    # Update user
    users.update_one({"email": email}, {
        "$inc": {
            "balance": stock["Price"],
            f"stockOwned.{UID}": -1,
            "portfolio": -stock["Price"]
        },
        "$push": {
            "transactionHistory": f"Sold {stock['Name']} at price {stock['Price']} on {datetime.utcnow().isoformat()}"
        }
    })

    return jsonify(success=True, message="Stock sold successfully.")


@app.route('/addcomment', methods=['POST'])
def add_comment():
    data = request.get_json()
    headline = data.get("headline")
    name = data.get("name")
    text = data.get("text")

    if not (headline and name and text):
        return jsonify({"message": "Missing fields"}), 400

    # Append the new comment to the commentArray in DB
    result = db['news'].update_one(
        {"headline": headline},
        {"$push": {"commentArray": {"name": name, "text": text}}}
    )

    if result.modified_count == 1:
        return jsonify({"message": "success"})
    else:
        return jsonify({"message": "notFound or error"}), 500
    
@app.route('/top-users', methods=['GET'])
def get_top_users():
    top_users = list(users.find().sort("portfolio", -1).limit(5))
    for user in top_users:
        user["_id"] = str(user["_id"])
        user.pop("password", None)
    return jsonify(top_users)

if __name__=="__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    







    
    
    
