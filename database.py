import os
import json
import mysql.connector
from mysql.connector import pooling
import bcrypt
from contextlib import contextmanager


class Database:
    def __init__(self):
        # Create connection pool for better connection management
        self.pool_config = {
            'pool_name': 'mypool',
            'pool_size': 5,  # Adjust based on your needs
            'host': os.getenv("MYSQL_DBHOST"),
            'user': os.getenv("MYSQL_USER"),
            'password': os.getenv("MYSQL_PASSWORD"),
            'database': os.getenv("MYSQL_DBNAME"),
            'charset': 'utf8mb4',
            'autocommit': True,
            'pool_reset_session': True
        }

        try:
            self.pool = mysql.connector.pooling.MySQLConnectionPool(**self.pool_config)
            print("Connection pool established successfully")
        except Exception as e:
            print(f"Error creating connection pool: {e}")
            # Fallback to single connection
            self.pool = None
            self._create_single_connection()

    def _create_single_connection(self):
        """Fallback method to create a single connection"""
        try:
            self.connection = mysql.connector.connect(
                host=os.getenv("MYSQL_DBHOST"),
                user=os.getenv("MYSQL_USER"),
                password=os.getenv("MYSQL_PASSWORD"),
                database=os.getenv("MYSQL_DBNAME"),
                charset='utf8mb4',
                autocommit=True
            )
            print("Single connection established successfully")
        except Exception as e:
            print(f"Error creating connection: {e}")
            self.connection = None

    @contextmanager
    def get_connection(self):
        """Context manager to get and properly manage database connections"""
        connection = None
        try:
            if self.pool:
                connection = self.pool.get_connection()
            else:
                # Check if single connection is still alive
                if hasattr(self, 'connection') and self.connection:
                    if not self.connection.is_connected():
                        self._create_single_connection()
                    connection = self.connection
                else:
                    self._create_single_connection()
                    connection = self.connection

            if connection and connection.is_connected():
                yield connection
            else:
                raise Exception("Could not establish database connection")

        except mysql.connector.Error as e:
            print(f"Database connection error: {e}")
            # Try to reconnect once
            if self.pool:
                try:
                    connection = self.pool.get_connection()
                    yield connection
                except:
                    raise Exception("Failed to reconnect to database")
            else:
                self._create_single_connection()
                if hasattr(self, 'connection') and self.connection:
                    yield self.connection
                else:
                    raise Exception("Failed to reconnect to database")
        finally:
            if connection and self.pool:
                # Return connection to pool
                connection.close()

    def insert_data(self, table_name, data_dict, user_context=None):
        """Insert data with proper connection management"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                columns = list(data_dict.keys())
                values = list(data_dict.values())

                # Create placeholders
                placeholders = ', '.join(['%s'] * len(columns))
                columns_str = ', '.join(columns)

                # Create a new record
                sql = f"INSERT INTO `{table_name}` ({columns_str}) VALUES ({placeholders})"
                cursor.execute(sql, values)
                record_id = cursor.lastrowid

                # Commit if autocommit is False
                if not connection.autocommit:
                    connection.commit()

                # Log the insert operation
                self.log_operation(
                    table_name=table_name,
                    operation='INSERT',
                    record_id=record_id,
                    data_after=data_dict,
                    user_context=user_context,
                    connection=connection
                )

                cursor.close()
                return record_id

        except Exception as e:
            print(f"Error inserting data: {e}")
            return False

    def log_operation(self, table_name, operation, record_id=None, data_before=None,
                      data_after=None, user_context=None, connection=None):
        """Log database operations for tracking"""
        try:
            # Use provided connection or get a new one
            if connection:
                cursor = connection.cursor()
                log_query = """
                INSERT INTO logs (table_name, operation, record_id, data_before, data_after, user_context)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                log_data = (
                    table_name,
                    operation,
                    record_id,
                    json.dumps(data_before) if data_before else None,
                    json.dumps(data_after) if data_after else None,
                    user_context or 'system'
                )
                cursor.execute(log_query, log_data)
                if not connection.autocommit:
                    connection.commit()
                cursor.close()
            else:
                # Get connection if not provided
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    log_query = """
                    INSERT INTO logs (table_name, operation, record_id, data_before, data_after, user_context)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    log_data = (
                        table_name,
                        operation,
                        record_id,
                        json.dumps(data_before) if data_before else None,
                        json.dumps(data_after) if data_after else None,
                        user_context or 'system'
                    )
                    cursor.execute(log_query, log_data)
                    if not conn.autocommit:
                        conn.commit()
                    cursor.close()

        except Exception as e:
            print(f"Error logging operation: {e}")

    def update_data(self, table_name, data, condition, user_context=None):
        """Update data with proper connection management"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()

                # First, get the current data for logging
                select_query = f"SELECT * FROM {table_name} WHERE {condition}"
                cursor.execute(select_query)
                current_data = cursor.fetchone()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

                # Perform the update
                set_clause = ', '.join([f"{key} = %s" for key in data.keys()])
                query = f"UPDATE {table_name} SET {set_clause} WHERE {condition}"

                cursor.execute(query, tuple(data.values()))

                if not connection.autocommit:
                    connection.commit()

                # Log the update operation
                if current_data and columns:
                    data_before = dict(zip(columns, current_data))
                    self.log_operation(
                        table_name=table_name,
                        operation='UPDATE',
                        data_before=data_before,
                        data_after=data,
                        user_context=user_context,
                        connection=connection
                    )

                cursor.close()
                return True

        except Exception as e:
            print(f"Error updating data: {e}")
            return False

    def get_pet_by_name(self, name, id):
        """Get pet profile by name"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                query = "SELECT * FROM pet_profile WHERE name = %s and owner = %s"
                cursor.execute(query, (name,id,))
                result = cursor.fetchone()
                cursor.close()
                return result

        except Exception as e:
            print(f"Error fetching pet data: {e}")
            return None

    def get_user_account(self, email, pwd):
        """Authenticate user account"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                query = "SELECT id, password FROM users WHERE email = %s"
                cursor.execute(query, (email,))
                data = cursor.fetchone()
                cursor.close()

                if data:
                    user_id, password = data
                    if bcrypt.checkpw(pwd.encode('utf-8'), password.encode('utf-8')):
                        return user_id
                return None

        except Exception as e:
            print(f"Error during login: {e}")
            return None

    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        """Generic method to execute queries"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                cursor.execute(query, params or ())

                if fetch_one:
                    result = cursor.fetchone()
                elif fetch_all:
                    result = cursor.fetchall()
                else:
                    result = cursor.rowcount

                if not connection.autocommit:
                    connection.commit()

                cursor.close()
                return result

        except Exception as e:
            print(f"Error executing query: {e}")
            return None

    def close(self):
        """Close all connections"""
        try:
            if self.pool:
                # Connection pool will handle cleanup automatically
                pass
            elif hasattr(self, 'connection') and self.connection:
                if self.connection.is_connected():
                    self.connection.close()
                    print("Single connection closed successfully")
        except Exception as e:
            print(f"Error closing connections: {e}")

    def __del__(self):
        """Cleanup when object is destroyed"""
        self.close()
