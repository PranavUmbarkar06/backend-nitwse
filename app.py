from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from pymongo import MongoClient
from flask_cors import CORS
import logging

# Initialize Flask application
app = Flask(__name__)

# Enable CORS for all routes (allows cross-origin requests)
CORS(app)

# Configure logging for better error tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB Atlas configuration
MONGO_URI = "mongodb+srv://nitwse:mayankthegoat@wse.0zosyhw.mongodb.net/nitwse?retryWrites=true&w=majority&appName=WSE"
app.config["MONGO_URI"] = MONGO_URI

# Initialize PyMongo for Flask integration
mongo = PyMongo(app)

# Initialize direct MongoDB client for specific operations
try:
    client = MongoClient("mongodb+srv://nitwse:mayankthegoat@wse.0zosyhw.mongodb.net/?retryWrites=true&w=majority&appName=WSE")
    db = client["nitwse"]
    users = db["users"]
    logger.info("MongoDB connection established successfully")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def updateBalance(userID, updatedPrice):
    """
    Updates the balance of a user by the specified amount.
    
    Args:
        userID (int): The ID of the user
        updatedPrice (float): The amount to add/subtract from balance (negative for deduction)
    
    Returns:
        bool: True if update successful, False if insufficient balance
    """
    try:
        # Find user's current balance
        temp = mongo.db.usertransactions.find_one({"userID": userID})
        if not temp:
            logger.error(f"User {userID} not found in usertransactions")
            return False
            
        # Check if the update would result in negative balance
        if temp["balance"] + updatedPrice < 0:
            logger.warning(f"Insufficient balance for user {userID}. Current: {temp['balance']}, Required: {abs(updatedPrice)}")
            return False
        else:
            # Update the user's balance
            mongo.db.usertransactions.update_one(
                {"userID": userID},
                {"$inc": {"balance": updatedPrice}}
            )
            logger.info(f"Balance updated for user {userID}. Change: {updatedPrice}")
            return True
    except Exception as e:
        logger.error(f"Error updating balance for user {userID}: {e}")
        return False

def buyStock(userID, stockPrice, quantity, stockName):
    """
    Handles the purchase of stocks for a user.
    
    Args:
        userID (int): The ID of the user
        stockPrice (float): Price per stock
        quantity (int): Number of stocks to buy
        stockName (str): Name of the stock
    
    Returns:
        bool: True if purchase successful, False otherwise
    """
    try:
        total_cost = stockPrice * quantity
        
        # First, deduct the money from balance
        if updateBalance(userID, -1 * total_cost):
            # Then, add the stocks to user's portfolio
            mongo.db.usertransactions.update_one(
                {"userID": userID},
                {"$inc": {f"stocksOwned.{stockName}": quantity}}
            )
            logger.info(f"Stock purchase successful for user {userID}: {quantity} shares of {stockName}")
            return True
        else:
            logger.warning(f"Stock purchase failed for user {userID}: Insufficient balance")
            return False
    except Exception as e:
        logger.error(f"Error in buyStock for user {userID}: {e}")
        return False

def sellStock(userID, stockPrice, quantity, stockName):
    """
    Handles the selling of stocks for a user.
    
    Args:
        userID (int): The ID of the user
        stockPrice (float): Price per stock
        quantity (int): Number of stocks to sell
        stockName (str): Name of the stock
    
    Returns:
        bool: True if sale successful, False otherwise
    """
    try:
        # Check if user has enough stocks to sell
        temp = mongo.db.usertransactions.find_one({"userID": userID})
        if not temp:
            logger.error(f"User {userID} not found in usertransactions")
            return False
            
        if stockName in temp["stocksOwned"] and temp["stocksOwned"][stockName] >= quantity:
            # Deduct stocks from user's portfolio
            mongo.db.usertransactions.update_one(
                {"userID": userID},
                {"$inc": {f"stocksOwned.{stockName}": -quantity}}
            )
            # Add money to user's balance
            updateBalance(userID, stockPrice * quantity)
            logger.info(f"Stock sale successful for user {userID}: {quantity} shares of {stockName}")
            return True
        else:
            logger.warning(f"Stock sale failed for user {userID}: Insufficient stocks. Required: {quantity}, Available: {temp['stocksOwned'].get(stockName, 0)}")
            return False
    except Exception as e:
        logger.error(f"Error in sellStock for user {userID}: {e}")
        return False

def get_next_user_id():
    """
    Generates the next available user ID by finding the highest existing ID.
    
    Returns:
        int: Next available user ID (starts from 1001 if no users exist)
    """
    try:
        # Find the user with the highest userId
        highest_user = users.find_one(sort=[("userId", -1)])
        if highest_user and "userId" in highest_user:
            next_id = highest_user["userId"] + 1
            logger.info(f"Generated new user ID: {next_id}")
            return next_id
        logger.info("No existing users found, starting from ID 1001")
        return 1001  # Start from 1001 if no users exist
    except Exception as e:
        logger.error(f"Error generating user ID: {e}")
        return 1001

# =============================================================================
# AUTHENTICATION ROUTES
# =============================================================================

@app.route('/signup', methods=['POST'])
def signup():
    """
    Handle user registration.
    Creates a new user account and initializes their portfolio with a starting balance.
    """
    try:
        # Parse JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({"message": "No JSON data provided", "success": False}), 400

        # Extract required fields
        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        if not (email.endswith("@student.nitw.ac.in") or email.endswith("@nitw.ac.in")):
            return jsonify({"message": "Use only your institute ID", "success": False}), 400
        # Validate required fields
        if not all([name, email, password]):
            return jsonify({"message": "Missing required fields (name, email, password)", "success": False}), 400

        # Check if user already exists
        if users.find_one({"email": email}):
            logger.warning(f"Signup attempt with existing email: {email}")
            return jsonify({"message": "User already exists", "success": False}), 409

        # Generate new user ID
        userId = get_next_user_id()

        # Insert user into users collection
        users.insert_one({
            "name": name,
            "email": email,
            "password": password,
            "userId": userId
        })

        # Initialize user portfolio with starting balance of 10,000
        db.usertransactions.insert_one({
            "userID": userId,
            "balance": 10000,
            "stocksOwned": {}
        })

        logger.info(f"New user registered successfully: {email} with ID {userId}")
        return jsonify({
            "message": "Signup successful",
            "success": True,
            "userId": userId,
            "name": name
        }), 201

    except Exception as e:
        logger.error(f"Error during signup: {e}")
        return jsonify({"message": "Internal server error during signup", "success": False}), 500

@app.route('/login', methods=['POST'])
def login():
    """
    Handle user authentication.
    Validates user credentials and returns user information if successful.
    """
    try:
        # Parse JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({"message": "No JSON data provided", "success": False}), 400

        # Extract credentials
        email = data.get("email")
        email=email.lower()
        password = data.get("password")

        # Validate required fields
        if not all([email, password]):
            return jsonify({"message": "Email and password are required", "success": False}), 400

        # Find user with matching credentials
        user = users.find_one({"email": email, "password": password})
        
        if user:
            logger.info(f"Successful login for user: {email}")
            return jsonify({
                "message": "Login successful",
                "success": True,
                "userId": user["userId"],
                "name": user["name"]
            }), 200
        else:
            logger.warning(f"Failed login attempt for email: {email}")
            return jsonify({"message": "Invalid credentials", "success": False}), 401

    except Exception as e:
        logger.error(f"Error during login: {e}")
        return jsonify({"message": "Internal server error during login", "success": False}), 500

# =============================================================================
# STOCK TRADING ROUTES
# =============================================================================

@app.route('/buy', methods=['POST'])
def buy():
    """
    Handle stock purchase transactions.
    Validates user balance and executes stock purchase if sufficient funds are available.
    """
    try:
        # Parse JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON received"}), 400

        # Validate required fields
        required_fields = ["userID", "stockPrice", "quantity", "stockName"]
        for field in required_fields:
            if field not in data:
                return jsonify({"status": "error", "message": f"Missing required field: {field}"}), 400

        # Extract and validate data types
        try:
            userID = int(data["userID"])
            stockPrice = float(data["stockPrice"])
            quantity = int(data["quantity"])
            stockName = data["stockName"]
        except (ValueError, TypeError) as e:
            return jsonify({"status": "error", "message": "Invalid data types provided"}), 400

        # Validate positive values
        if quantity <= 0 or stockPrice <= 0:
            return jsonify({"status": "error", "message": "Quantity and stock price must be positive"}), 400

        # Calculate total cost
        total_cost = stockPrice * quantity

        # Execute atomic transaction: check balance and update both balance and stocks
        result = mongo.db.usertransactions.update_one(
            {
                "userID": userID,
                "balance": {"$gte": total_cost}  # Ensure sufficient balance
            },
            {
                "$inc": {
                    "balance": -total_cost,  # Deduct money
                    f"stocksOwned.{stockName}": quantity  # Add stocks
                }
            }
        )

        if result.modified_count == 1:
            logger.info(f"Stock purchase successful - User {userID}: {quantity} shares of {stockName} for ${total_cost}")
            return jsonify({"status": "success", "message": "Transaction Successful"})
        else:
            logger.warning(f"Stock purchase failed - User {userID}: Insufficient balance for {quantity} shares of {stockName}")
            return jsonify({"status": "failed", "message": "Invalid Transaction or Insufficient balance"})

    except Exception as e:
        logger.error(f"Error in buy route: {e}")
        return jsonify({"status": "error", "message": "Internal server error during purchase"}), 500

@app.route('/sell', methods=['POST'])
def sell():
    """
    Handle stock selling transactions.
    Validates user's stock holdings and executes sale if sufficient stocks are available.
    """
    try:
        # Parse JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON received"}), 400

        # Validate required fields
        required_keys = ["userID", "stockPrice", "quantity", "stockName"]
        for key in required_keys:
            if key not in data:
                return jsonify({"status": "error", "message": f"Missing key: {key}"}), 400

        # Extract and validate data types
        try:
            userID = int(data["userID"])
            stockPrice = float(data["stockPrice"])
            quantity = int(data["quantity"])
            stockName = data["stockName"]
        except ValueError:
            return jsonify({"status": "error", "message": "Invalid data types"}), 400

        # Validate positive values
        if quantity <= 0 or stockPrice <= 0:
            return jsonify({"status": "error", "message": "Quantity and stockPrice must be positive"}), 400

        # Execute stock sale using utility function
        if sellStock(userID, stockPrice, quantity, stockName):
            return jsonify({"status": "success", "message": "Transaction Successful"})
        else:
            return jsonify({"status": "failed", "message": "Invalid Transaction - Insufficient stocks or user not found"})

    except Exception as e:
        logger.error(f"Error in sell route: {e}")
        return jsonify({"status": "error", "message": "Internal server error during sale"}), 500

# =============================================================================
# DATA RETRIEVAL ROUTES
# =============================================================================

@app.route('/import', methods=['GET'])
def display():
    """
    Retrieve user's portfolio information including balance and stock holdings.
    """
    try:
        # Get userID from query parameters
        user_id_param = request.args.get("userID")
        if not user_id_param:
            return jsonify({"error": "userID parameter is required"}), 400

        # Validate userID format
        try:
            userID = int(user_id_param)
        except ValueError:
            return jsonify({"error": "userID must be a valid integer"}), 400

        # Find user's portfolio data
        user = mongo.db.usertransactions.find_one({"userID": userID})
        
        if user:
            logger.info(f"Portfolio data retrieved for user {userID}")
            return jsonify({
                "balance": user["balance"],
                "stocks": user["stocksOwned"]
            })
        else:
            logger.warning(f"Portfolio data not found for user {userID}")
            return jsonify({
                "error": "User not found",
                "stocks": {}
            }), 404

    except Exception as e:
        logger.error(f"Error in display route: {e}")
        return jsonify({"error": "Internal server error while retrieving user data"}), 500

@app.route('/get_stocks', methods=['GET'])
def get_stocks():
    """
    Retrieve all available stocks with their current prices.
    Returns a dictionary with stock names as keys and stock details as values.
    """
    try:
        # Fetch all stocks from database (excluding MongoDB's _id field)
        stocks = list(mongo.db.stockdata.find({}, {"_id": 0}))
        
        # Transform data into desired format
        result = {}
        for stock in stocks:
            if 'Name' in stock and 'Price' in stock:
                result[stock['Name']] = {
                    "Name": stock['Name'],
                    "Price": stock['Price']
                }

        logger.info(f"Retrieved {len(result)} stocks from database")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in get_stocks route: {e}")
        return jsonify({"error": "Internal server error while retrieving stocks"}), 500

@app.route('/get_remaining_stocks', methods=['GET'])
def get_remaining_stocks():
    """
    Get stocks that a specific user doesn't own yet.
    Useful for showing available stocks for purchase.
    """
    try:
        # Get userID from query parameters
        user_id = request.args.get('userID')
        if not user_id:
            return jsonify({"error": "userID is required"}), 400

        # Validate userID format
        try:
            user_id = int(user_id)
        except ValueError:
            return jsonify({"error": "userID must be an integer"}), 400

        # Get user's current stock holdings
        user_data = mongo.db.userdata.find_one({"userID": user_id}, {"_id": 0, "stocksOwned": 1})
        user_stocks = set(user_data.get("stocksOwned", {}).keys()) if user_data else set()

        # Get all available stocks
        all_stocks = list(mongo.db.stockdata.find({}, {"_id": 0}))

        # Filter out stocks the user already owns
        remaining_stocks = [stock for stock in all_stocks if stock.get('Name') not in user_stocks]

        logger.info(f"Retrieved {len(remaining_stocks)} remaining stocks for user {user_id}")
        return jsonify({"remaining_stocks": remaining_stocks})

    except Exception as e:
        logger.error(f"Error in get_remaining_stocks route: {e}")
        return jsonify({"error": "Internal server error while retrieving remaining stocks"}), 500

# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors - Route not found"""
    return jsonify({"error": "Route not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors - Method not allowed"""
    return jsonify({"error": "Method not allowed for this route"}), 405

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors - Internal server error"""
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# =============================================================================
# APPLICATION ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    logger.info("Starting Flask application...")
    # Run the application in debug mode
    # In production, set debug=False and configure proper logging
    app.run(debug=True, host='0.0.0.0', port=5000)
