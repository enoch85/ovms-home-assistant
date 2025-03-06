"""Error handling utilities for OVMS integration."""
import logging
import asyncio
from typing import Any, Callable, Dict, Optional, Tuple, Type, Union

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..const import (
    LOGGER_NAME,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_TIMEOUT,
    ERROR_INVALID_RESPONSE,
    ERROR_NO_TOPICS,
    ERROR_TOPIC_ACCESS_DENIED,
    ERROR_TLS_ERROR, 
    ERROR_UNKNOWN,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

class OVMSError(HomeAssistantError):
    """Base class for OVMS errors."""
    
    def __init__(self, message: str, error_type: str = ERROR_UNKNOWN, details: Optional[Dict[str, Any]] = None):
        """Initialize the error.
        
        Args:
            message: Error message
            error_type: Error type code for UI
            details: Additional error details
        """
        super().__init__(message)
        self.error_type = error_type
        self.details = details or {}
        

class ConnectionError(OVMSError):
    """Error connecting to OVMS or MQTT broker."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize the error."""
        super().__init__(message, ERROR_CANNOT_CONNECT, details)
        

class AuthError(OVMSError):
    """Authentication error with OVMS or MQTT broker."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize the error."""
        super().__init__(message, ERROR_INVALID_AUTH, details)
        

class TimeoutError(OVMSError):
    """Timeout error with OVMS or MQTT broker."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize the error."""
        super().__init__(message, ERROR_TIMEOUT, details)
        

class ResponseError(OVMSError):
    """Invalid response from OVMS or MQTT broker."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize the error."""
        super().__init__(message, ERROR_INVALID_RESPONSE, details)
        

class NoTopicsError(OVMSError):
    """No OVMS topics found."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize the error."""
        super().__init__(message, ERROR_NO_TOPICS, details)
        

class TopicAccessError(OVMSError):
    """Topic access denied."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize the error."""
        super().__init__(message, ERROR_TOPIC_ACCESS_DENIED, details)
        

class TLSError(OVMSError):
    """TLS/SSL error."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize the error."""
        super().__init__(message, ERROR_TLS_ERROR, details)


async def async_handle_errors(
    hass: HomeAssistant,
    func: Callable,
    *args,
    log_errors: bool = True,
    reraise: bool = True,
    **kwargs
) -> Tuple[bool, Any, Optional[OVMSError]]:
    """Handle errors from async functions.
    
    Args:
        hass: HomeAssistant instance
        func: Function to call
        *args: Arguments to pass to the function
        log_errors: Whether to log errors
        reraise: Whether to reraise the error
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        Tuple of (success, result, error) where error is None on success
    """
    try:
        result = await func(*args, **kwargs)
        return True, result, None
    except OVMSError as err:
        if log_errors:
            _LOGGER.error("Error calling %s: %s (%s)", func.__name__, err, err.error_type)
        if reraise:
            raise
        return False, None, err
    except asyncio.TimeoutError as err:
        error = TimeoutError(f"Timeout calling {func.__name__}", {"original_error": str(err)})
        if log_errors:
            _LOGGER.error("Timeout calling %s: %s", func.__name__, err)
        if reraise:
            raise error
        return False, None, error
    except Exception as err:  # pylint: disable=broad-except
        error = OVMSError(f"Unexpected error calling {func.__name__}: {err}")
        if log_errors:
            _LOGGER.exception("Unexpected error calling %s", func.__name__)
        if reraise:
            raise error
        return False, None, error


def map_error(exception: Exception, default_type: str = ERROR_UNKNOWN) -> str:
    """Map an exception to an error type.
    
    Args:
        exception: The exception to map
        default_type: Default error type to use if no match is found
        
    Returns:
        Error type code for UI
    """
    error_map = {
        ConnectionError: ERROR_CANNOT_CONNECT,
        AuthError: ERROR_INVALID_AUTH,
        TimeoutError: ERROR_TIMEOUT,
        ResponseError: ERROR_INVALID_RESPONSE,
        NoTopicsError: ERROR_NO_TOPICS,
        TopicAccessError: ERROR_TOPIC_ACCESS_DENIED,
        TLSError: ERROR_TLS_ERROR,
    }
    
    for error_class, error_type in error_map.items():
        if isinstance(exception, error_class):
            return error_type
            
    return default_type


def create_error_result(
    exception: Exception, 
    include_details: bool = True
) -> Dict[str, Any]:
    """Create a standardized error result dictionary.
    
    Args:
        exception: The exception to map
        include_details: Whether to include details in the result
        
    Returns:
        Error result dictionary
    """
    error_type = map_error(exception)
    
    result = {
        "success": False,
        "error_type": error_type,
        "message": str(exception),
    }
    
    if include_details and hasattr(exception, "details"):
        result["details"] = getattr(exception, "details")
        
    return result
