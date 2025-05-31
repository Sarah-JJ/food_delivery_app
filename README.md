# Food Delivery Service - Odoo Integration Assessment

## Overview

This repository contains the technical implementation for integrating a food delivery service mobile application with Odoo ERP system (Version 18). The project demonstrates the migration strategy, integration scripts, and workflow implementations for settlement and refund processes.


### 🔧 Setup Guide

1. make sure to create the database mobile_app_database in your postgres server and then run script
   ```scripts/mobile_app_database_seed.sql```
   
   This script creates the complete database schema and populates it with realistic sample data including.  
   **IMPORTANT: if you will run the Settlement Creation cron manually, the created_at date of seeded orders table records has to be *before* last Monday** 
2. Install odoo v18 including odoo enterprise modules, because the app depends on accounting
3. Modify system parameters `param_external_db_host`, `param_external_db_name`, `param_external_db_user`, `param_external_db_password`, and `param_external_db_port` in `data/system_parameters.xml`
4. Install modules: accounting, food_delivery


---

**Author**: Sarah Juhain  
**Position**: System Analyst Candidate  
**Date**: May 2025  
