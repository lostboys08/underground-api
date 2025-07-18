from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from config.supabase_client import supabase_service, get_user_client
import logging

router = APIRouter(prefix="/users", tags=["Users"])

# Pydantic models for request/response
class UserCreate(BaseModel):
    email: EmailStr
    name: str
    age: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    age: Optional[int]
    metadata: Optional[Dict[str, Any]]
    created_at: str
    updated_at: Optional[str]

# Dependency to extract JWT from Authorization header
async def get_jwt_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract JWT token from Authorization header"""
    if not authorization:
        return None
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() == "bearer":
            return token
    except ValueError:
        pass
    
    return None

@router.post("/", response_model=UserResponse)
async def create_user(user: UserCreate):
    """
    Create a new user in the database
    Uses service role client for admin access
    """
    try:
        # Insert user into Supabase
        result = supabase_service.table("users").insert({
            "email": user.email,
            "name": user.name,
            "age": user.age,
            "metadata": user.metadata or {}
        }).execute()
        
        if not result.data:
            raise HTTPException(status_code=400, detail="Failed to create user")
        
        created_user = result.data[0]
        return UserResponse(**created_user)
        
    except Exception as e:
        logging.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int):
    """
    Get a user by ID
    Uses service role client
    """
    try:
        result = supabase_service.table("users").select("*").eq("id", user_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = result.data[0]
        return UserResponse(**user)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/", response_model=List[UserResponse])
async def list_users(limit: int = 10, offset: int = 0):
    """
    List all users with pagination
    Uses service role client
    """
    try:
        result = (supabase_service.table("users")
                 .select("*")
                 .range(offset, offset + limit - 1)
                 .execute())
        
        users = [UserResponse(**user) for user in result.data]
        return users
        
    except Exception as e:
        logging.error(f"Error listing users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_update: UserUpdate):
    """
    Update a user by ID
    Uses service role client
    """
    try:
        # Build update data (only include non-None fields)
        update_data = {}
        if user_update.name is not None:
            update_data["name"] = user_update.name
        if user_update.age is not None:
            update_data["age"] = user_update.age
        if user_update.metadata is not None:
            update_data["metadata"] = user_update.metadata
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        result = (supabase_service.table("users")
                 .update(update_data)
                 .eq("id", user_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        updated_user = result.data[0]
        return UserResponse(**updated_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/{user_id}")
async def delete_user(user_id: int):
    """
    Delete a user by ID
    Uses service role client
    """
    try:
        result = supabase_service.table("users").delete().eq("id", user_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {"message": f"User {user_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Protected route example using JWT authentication
@router.get("/profile/me", response_model=UserResponse)
async def get_my_profile(jwt_token: Optional[str] = Depends(get_jwt_token)):
    """
    Get current user's profile using JWT authentication
    Demonstrates RLS (Row Level Security) usage
    """
    if not jwt_token:
        raise HTTPException(status_code=401, detail="Authorization token required")
    
    try:
        # Use authenticated client that respects RLS policies
        user_client = get_user_client(jwt_token)
        
        # This will only return the current user's data due to RLS
        result = user_client.table("users").select("*").execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="User profile not found")
        
        user = result.data[0]
        return UserResponse(**user)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching user profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Authentication or database error: {str(e)}")

@router.put("/profile/me", response_model=UserResponse)
async def update_my_profile(
    user_update: UserUpdate, 
    jwt_token: Optional[str] = Depends(get_jwt_token)
):
    """
    Update current user's profile using JWT authentication
    Demonstrates RLS (Row Level Security) usage
    """
    if not jwt_token:
        raise HTTPException(status_code=401, detail="Authorization token required")
    
    try:
        # Build update data (only include non-None fields)
        update_data = {}
        if user_update.name is not None:
            update_data["name"] = user_update.name
        if user_update.age is not None:
            update_data["age"] = user_update.age
        if user_update.metadata is not None:
            update_data["metadata"] = user_update.metadata
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Use authenticated client that respects RLS policies
        user_client = get_user_client(jwt_token)
        
        # This will only update the current user's data due to RLS
        result = user_client.table("users").update(update_data).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="User profile not found or unauthorized")
        
        updated_user = result.data[0]
        return UserResponse(**updated_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating user profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Authentication or database error: {str(e)}") 