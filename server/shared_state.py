# server/shared_state.py
import threading
import logging
import time

# Configure logging
logger = logging.getLogger("SharedState")

# Thread-safe global state for active houses and connected clients
class SharedState:
    def __init__(self):
        # Houses in memory
        self.active_houses = {}
        self.active_houses_lock = threading.Lock()  # Standard lock instead of RLock
        
        # Connected clients (from websocket_server)
        self.clients = {}
        self.clients_lock = threading.Lock()  # Standard lock instead of RLock
        
        # Server instance
        self.server = None
        self.server_lock = threading.Lock()
        
        # Lock timeout in seconds
        self.lock_timeout = 5.0
        
        logger.info("SharedState initialized")
    
    # House management methods with timeouts and deadlock prevention
    def get_house(self, house_id):
        lock_acquired = False
        try:
            # Try to acquire lock with timeout
            lock_acquired = self.active_houses_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning(f"Timeout acquiring houses lock for get_house({house_id})")
                return None
                
            return self.active_houses.get(house_id)
        except Exception as e:
            logger.error(f"Error retrieving house {house_id}: {str(e)}")
            return None
        finally:
            # Only release if we actually acquired the lock
            if lock_acquired:
                self.active_houses_lock.release()
    
    def add_house(self, house_id, house):
        lock_acquired = False
        try:
            # Try to acquire lock with timeout
            lock_acquired = self.active_houses_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning(f"Timeout acquiring houses lock for add_house({house_id})")
                raise TimeoutError(f"Timeout adding house {house_id}")
                
            self.active_houses[house_id] = house
            logger.debug(f"House {house_id} added to shared state")
            return house
        except Exception as e:
            logger.error(f"Error adding house {house_id} to shared state: {str(e)}")
            raise
        finally:
            if lock_acquired:
                self.active_houses_lock.release()
    
    def remove_house(self, house_id):
        lock_acquired = False
        try:
            lock_acquired = self.active_houses_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning(f"Timeout acquiring houses lock for remove_house({house_id})")
                raise TimeoutError(f"Timeout removing house {house_id}")
                
            if house_id in self.active_houses:
                house = self.active_houses.pop(house_id)
                logger.debug(f"House {house_id} removed from shared state")
                return house
            else:
                logger.warning(f"Attempted to remove non-existent house {house_id}")
                return None
        except Exception as e:
            logger.error(f"Error removing house {house_id} from shared state: {str(e)}")
            raise
        finally:
            if lock_acquired:
                self.active_houses_lock.release()
    
    def get_all_houses(self):
        lock_acquired = False
        try:
            lock_acquired = self.active_houses_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning("Timeout acquiring houses lock for get_all_houses()")
                return {}
                
            # Return a copy to avoid concurrent modification
            houses_copy = self.active_houses.copy()
            return houses_copy
        except Exception as e:
            logger.error(f"Error getting all houses: {str(e)}")
            return {}
        finally:
            if lock_acquired:
                self.active_houses_lock.release()
    
    # Client management methods with timeouts and deadlock prevention
    def get_client(self, client_id):
        lock_acquired = False
        try:
            lock_acquired = self.clients_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning(f"Timeout acquiring clients lock for get_client({client_id})")
                return None
                
            return self.clients.get(client_id)
        except Exception as e:
            logger.error(f"Error retrieving client {client_id}: {str(e)}")
            return None
        finally:
            if lock_acquired:
                self.clients_lock.release()
    
    def add_client(self, client_id, client_data):
        lock_acquired = False
        try:
            lock_acquired = self.clients_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning(f"Timeout acquiring clients lock for add_client({client_id})")
                raise TimeoutError(f"Timeout adding client {client_id}")
                
            self.clients[client_id] = client_data
            logger.debug(f"Client {client_id} added to shared state")
        except Exception as e:
            logger.error(f"Error adding client {client_id} to shared state: {str(e)}")
            raise
        finally:
            if lock_acquired:
                self.clients_lock.release()
    
    def remove_client(self, client_id):
        lock_acquired = False
        try:
            lock_acquired = self.clients_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning(f"Timeout acquiring clients lock for remove_client({client_id})")
                raise TimeoutError(f"Timeout removing client {client_id}")
                
            if client_id in self.clients:
                client_data = self.clients.pop(client_id)
                logger.debug(f"Client {client_id} removed from shared state")
                return client_data
            else:
                logger.warning(f"Attempted to remove non-existent client {client_id}")
                return None
        except Exception as e:
            logger.error(f"Error removing client {client_id} from shared state: {str(e)}")
            raise
        finally:
            if lock_acquired:
                self.clients_lock.release()
    
    def update_client(self, client_id, updates):
        lock_acquired = False
        try:
            lock_acquired = self.clients_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning(f"Timeout acquiring clients lock for update_client({client_id})")
                raise TimeoutError(f"Timeout updating client {client_id}")
                
            if client_id in self.clients:
                self.clients[client_id].update(updates)
                logger.debug(f"Client {client_id} updated in shared state")
            else:
                logger.warning(f"Attempted to update non-existent client {client_id}")
        except Exception as e:
            logger.error(f"Error updating client {client_id} in shared state: {str(e)}")
            raise
        finally:
            if lock_acquired:
                self.clients_lock.release()
    
    def get_house_clients(self, house_id):
        """Get all clients connected to a specific house"""
        lock_acquired = False
        try:
            clients_in_house = {}
            lock_acquired = self.clients_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning(f"Timeout acquiring clients lock for get_house_clients({house_id})")
                return {}
                
            for client_id, client_data in self.clients.items():
                if client_data.get('house_id') == house_id:
                    clients_in_house[client_id] = client_data
            return clients_in_house
        except Exception as e:
            logger.error(f"Error getting clients for house {house_id}: {str(e)}")
            return {}
        finally:
            if lock_acquired:
                self.clients_lock.release()
    
    # Server management with timeouts and deadlock prevention
    def set_server(self, server):
        lock_acquired = False
        try:
            lock_acquired = self.server_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning("Timeout acquiring server lock for set_server()")
                raise TimeoutError("Timeout setting server reference")
                
            self.server = server
            logger.debug("Server reference updated in shared state")
        except Exception as e:
            logger.error(f"Error setting server reference: {str(e)}")
            raise
        finally:
            if lock_acquired:
                self.server_lock.release()
    
    def get_server(self):
        lock_acquired = False
        try:
            lock_acquired = self.server_lock.acquire(timeout=self.lock_timeout)
            if not lock_acquired:
                logger.warning("Timeout acquiring server lock for get_server()")
                return None
                
            return self.server
        except Exception as e:
            logger.error(f"Error retrieving server reference: {str(e)}")
            return None
        finally:
            if lock_acquired:
                self.server_lock.release()
                
    # Additional method to detect and break potential deadlocks
    def check_for_deadlocks(self):
        """
        Check if any locks have been held for too long and log warnings.
        This could be called from a monitoring thread.
        """
        # In a production system, you might track lock acquisition times
        # and use this method to detect and potentially break deadlocks
        pass

# Create a singleton instance
state = SharedState()