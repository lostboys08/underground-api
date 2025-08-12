from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from config.supabase_client import get_service_client
from utils.auth import get_current_user_id
from utils.encryption import encrypt_password, decrypt_password
import logging

router = APIRouter(prefix="/companies", tags=["Companies"])

# Pydantic models for request/response
class CompanyCreate(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    bluestakes_username: Optional[str] = None
    bluestakes_password: Optional[str] = None

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    bluestakes_username: Optional[str] = None
    bluestakes_password: Optional[str] = None

class CompanyResponse(BaseModel):
    id: int
    name: str
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    bluestakes_username: Optional[str]
    created_at: str
    updated_at: str
    # Note: we don't expose the encrypted password in responses

class CompanyWithProjects(CompanyResponse):
    project_count: Optional[int] = None

@router.post("/", response_model=CompanyResponse)
async def create_company(company: CompanyCreate):
    """
    Create a new company
    """
    try:
        # Prepare data for insertion
        insert_data = {
            "name": company.name,
            "address": company.address,
            "city": company.city,
            "state": company.state,
            "zip": company.zip,
            "phone": company.phone,
            "email": company.email,
            "bluestakes_username": company.bluestakes_username
        }
        
        # Encrypt password if provided
        if company.bluestakes_password:
            insert_data["bluestakes_password_encrypted"] = encrypt_password(company.bluestakes_password)
        
        result = get_service_client().table("companies").insert(insert_data).execute()
        
        if not result.data:
            raise HTTPException(status_code=400, detail="Failed to create company")
        
        created_company = result.data[0]
        return CompanyResponse(**created_company)
        
    except Exception as e:
        logging.error(f"Error creating company: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: int):
    """
    Get a company by ID
    """
    try:
        result = get_service_client().table("companies").select("*").eq("id", company_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Company not found")
        
        company = result.data[0]
        return CompanyResponse(**company)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching company {company_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/", response_model=List[CompanyWithProjects])
async def list_companies(
    limit: int = Query(default=10, le=100),
    offset: int = Query(default=0, ge=0)
):
    """
    List companies with project counts
    """
    try:
        # Get companies with project counts
        result = (get_service_client().table("companies")
                 .select("*, projects(count)")
                 .range(offset, offset + limit - 1)
                 .execute())
        
        companies = []
        for company in result.data:
            company_data = {**company}
            # Extract project count from the nested projects array
            project_count = len(company.get("projects", []))
            company_data["project_count"] = project_count
            
            # Remove the nested projects object
            if "projects" in company_data:
                del company_data["projects"]
            
            companies.append(CompanyWithProjects(**company_data))
        
        return companies
        
    except Exception as e:
        logging.error(f"Error listing companies: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(company_id: int, company_update: CompanyUpdate):
    """
    Update a company by ID
    """
    try:
        # Build update data (only include non-None fields)
        update_data = {}
        if company_update.name is not None:
            update_data["name"] = company_update.name
        if company_update.address is not None:
            update_data["address"] = company_update.address
        if company_update.city is not None:
            update_data["city"] = company_update.city
        if company_update.state is not None:
            update_data["state"] = company_update.state
        if company_update.zip is not None:
            update_data["zip"] = company_update.zip
        if company_update.phone is not None:
            update_data["phone"] = company_update.phone
        if company_update.email is not None:
            update_data["email"] = company_update.email
        if company_update.bluestakes_username is not None:
            update_data["bluestakes_username"] = company_update.bluestakes_username
        if company_update.bluestakes_password is not None:
            update_data["bluestakes_password_encrypted"] = encrypt_password(company_update.bluestakes_password)
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        result = (get_service_client().table("companies")
                 .update(update_data)
                 .eq("id", company_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Company not found")
        
        updated_company = result.data[0]
        return CompanyResponse(**updated_company)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating company {company_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/{company_id}")
async def delete_company(company_id: int):
    """
    Delete a company by ID
    Note: This might fail if there are related records (projects, profiles, etc.)
    """
    try:
        result = get_service_client().table("companies").delete().eq("id", company_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Company not found")
        
        return {"message": f"Company {company_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting company {company_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/{company_id}/bluestakes-credentials")
async def get_company_bluestakes_credentials(
    company_id: int,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get Bluestakes credentials for a company (admin only)
    Returns decrypted credentials for API usage
    """
    try:
        # Check if user has access to this company
        profile_result = (get_service_client().table("profiles")
                         .select("company_id, role")
                         .eq("user_id", current_user_id)
                         .execute())
        
        if not profile_result.data:
            raise HTTPException(status_code=403, detail="User profile not found")
        
        profile = profile_result.data[0]
        user_company_id = profile.get("company_id")
        user_role = profile.get("role")
        
        # Check if user belongs to this company or is an admin
        if user_company_id != company_id and user_role != "admin":
            raise HTTPException(status_code=403, detail="Access denied to company credentials")
        
        # Get company with encrypted credentials
        result = (get_service_client().table("companies")
                 .select("bluestakes_username, bluestakes_password_encrypted")
                 .eq("id", company_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Company not found")
        
        company = result.data[0]
        
        # Decrypt password if it exists
        decrypted_password = None
        if company.get("bluestakes_password_encrypted"):
            try:
                decrypted_password = decrypt_password(company["bluestakes_password_encrypted"])
            except Exception as e:
                logging.error(f"Error decrypting password: {str(e)}")
                raise HTTPException(status_code=500, detail="Error decrypting credentials")
        
        return {
            "bluestakes_username": company.get("bluestakes_username"),
            "bluestakes_password": decrypted_password,
            "has_credentials": bool(company.get("bluestakes_username") and company.get("bluestakes_password_encrypted"))
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting company credentials: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}") 