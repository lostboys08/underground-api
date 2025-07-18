from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from uuid import UUID
from config.supabase_client import get_service_client, get_user_client
from utils.auth import get_current_user_id, get_current_user_optional
import logging

router = APIRouter(prefix="/profiles", tags=["User Profiles"])

# Pydantic models for request/response
class ProfileCreate(BaseModel):
    user_id: UUID
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    website_url: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = "user"
    company_id: Optional[int] = None

class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    website_url: Optional[str] = None
    email: Optional[EmailStr] = None
    company_id: Optional[int] = None

class ProfileResponse(BaseModel):
    id: int
    user_id: UUID
    display_name: Optional[str]
    avatar_url: Optional[str]
    website_url: Optional[str]
    email: Optional[str]
    role: str
    company_id: Optional[int]
    created_at: str
    updated_at: str

class ProfileWithCompany(ProfileResponse):
    company_name: Optional[str] = None

@router.post("/", response_model=ProfileResponse)
async def create_profile(profile: ProfileCreate):
    """
    Create a new user profile
    Uses service role client for admin access
    """
    try:
        # Insert profile into Supabase
        result = get_service_client().table("profiles").insert({
            "user_id": str(profile.user_id),
            "display_name": profile.display_name,
            "avatar_url": profile.avatar_url,
            "website_url": profile.website_url,
            "email": profile.email,
            "role": profile.role,
            "company_id": profile.company_id
        }).execute()
        
        if not result.data:
            raise HTTPException(status_code=400, detail="Failed to create profile")
        
        created_profile = result.data[0]
        return ProfileResponse(**created_profile)
        
    except Exception as e:
        logging.error(f"Error creating profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/{profile_id}", response_model=ProfileWithCompany)
async def get_profile(profile_id: int):
    """
    Get a profile by ID with company information
    """
    try:
        result = (get_service_client().table("profiles")
                 .select("*, companies(name)")
                 .eq("id", profile_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        profile = result.data[0]
        
        # Format the response to include company name
        response_data = {
            **profile,
            "company_name": profile.get("companies", {}).get("name") if profile.get("companies") else None
        }
        
        # Remove the nested companies object
        if "companies" in response_data:
            del response_data["companies"]
        
        return ProfileWithCompany(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching profile {profile_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/", response_model=List[ProfileWithCompany])
async def list_profiles(
    limit: int = Query(default=10, le=100),
    offset: int = Query(default=0, ge=0),
    company_id: Optional[int] = Query(default=None),
    role: Optional[str] = Query(default=None)
):
    """
    List profiles with optional filtering by company and role
    """
    try:
        query = (get_service_client().table("profiles")
                .select("*, companies(name)")
                .range(offset, offset + limit - 1))
        
        # Add filters if provided
        if company_id:
            query = query.eq("company_id", company_id)
        if role:
            query = query.eq("role", role)
        
        result = query.execute()
        
        # Format the response to include company names
        profiles = []
        for profile in result.data:
            response_data = {
                **profile,
                "company_name": profile.get("companies", {}).get("name") if profile.get("companies") else None
            }
            # Remove the nested companies object
            if "companies" in response_data:
                del response_data["companies"]
            profiles.append(ProfileWithCompany(**response_data))
        
        return profiles
        
    except Exception as e:
        logging.error(f"Error listing profiles: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: int, profile_update: ProfileUpdate):
    """
    Update a profile by ID
    Uses service role client
    """
    try:
        # Build update data (only include non-None fields)
        update_data = {}
        if profile_update.display_name is not None:
            update_data["display_name"] = profile_update.display_name
        if profile_update.avatar_url is not None:
            update_data["avatar_url"] = profile_update.avatar_url
        if profile_update.website_url is not None:
            update_data["website_url"] = profile_update.website_url
        if profile_update.email is not None:
            update_data["email"] = profile_update.email
        if profile_update.company_id is not None:
            update_data["company_id"] = profile_update.company_id
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        result = (get_service_client().table("profiles")
                 .update(update_data)
                 .eq("id", profile_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        updated_profile = result.data[0]
        return ProfileResponse(**updated_profile)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating profile {profile_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/{profile_id}")
async def delete_profile(profile_id: int):
    """
    Delete a profile by ID
    Uses service role client
    """
    try:
        result = get_service_client().table("profiles").delete().eq("id", profile_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        return {"message": f"Profile {profile_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting profile {profile_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Protected route - get current user's profile
@router.get("/me/profile", response_model=ProfileWithCompany)
async def get_my_profile(current_user_id: str = Depends(get_current_user_id)):
    """
    Get current authenticated user's profile
    """
    try:
        result = (get_service_client().table("profiles")
                 .select("*, companies(name)")
                 .eq("user_id", current_user_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        profile = result.data[0]
        
        # Format the response to include company name
        response_data = {
            **profile,
            "company_name": profile.get("companies", {}).get("name") if profile.get("companies") else None
        }
        
        # Remove the nested companies object
        if "companies" in response_data:
            del response_data["companies"]
        
        return ProfileWithCompany(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching current user profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/me/profile", response_model=ProfileResponse)
async def update_my_profile(
    profile_update: ProfileUpdate,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Update current authenticated user's profile
    """
    try:
        # Build update data (only include non-None fields)
        update_data = {}
        if profile_update.display_name is not None:
            update_data["display_name"] = profile_update.display_name
        if profile_update.avatar_url is not None:
            update_data["avatar_url"] = profile_update.avatar_url
        if profile_update.website_url is not None:
            update_data["website_url"] = profile_update.website_url
        if profile_update.email is not None:
            update_data["email"] = profile_update.email
        if profile_update.company_id is not None:
            update_data["company_id"] = profile_update.company_id
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Update only the current user's profile
        result = (get_service_client().table("profiles")
                 .update(update_data)
                 .eq("user_id", current_user_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        updated_profile = result.data[0]
        return ProfileResponse(**updated_profile)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating current user profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/by-user/{user_id}", response_model=ProfileWithCompany)
async def get_profile_by_user_id(user_id: UUID):
    """
    Get a profile by user_id (auth.users.id)
    """
    try:
        result = (get_service_client().table("profiles")
                 .select("*, companies(name)")
                 .eq("user_id", str(user_id))
                 .execute())
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        profile = result.data[0]
        
        # Format the response to include company name
        response_data = {
            **profile,
            "company_name": profile.get("companies", {}).get("name") if profile.get("companies") else None
        }
        
        # Remove the nested companies object
        if "companies" in response_data:
            del response_data["companies"]
        
        return ProfileWithCompany(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching profile for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}") 