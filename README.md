# Food Delivery Service - Odoo Integration Assessment

## Overview

This repository contains the technical implementation for integrating a food delivery service mobile application with Odoo ERP system (Version 18). The project demonstrates the migration strategy, integration scripts, and workflow implementations for settlement and refund processes.


### 🔧 Installation

1. make sure to create the database mobile_app_database in your postgres server and then run script
   ```scripts/mobile_app_database_seed.sql```
   
   This script creates the complete database schema and populates it with realistic sample data including.

2. Install odoo v18 including odoo enterprise modules, because the app depends on accounting
3. Modify system parameters `param_external_db_host`, `param_external_db_name`, `param_external_db_user`, `param_external_db_password`, and `param_external_db_port` in `data/system_parameters.xml`
4. Install the module food_delivery either using the cmd by appending `-i food_delivery` to odoo's run command, or from the UI


---

**Author**: Sarah Juhain  
**Position**: System Analyst Candidate  
**Date**: May 2025  
