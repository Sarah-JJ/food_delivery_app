-- Create customers table
CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    customer_full_name VARCHAR(255) NOT NULL,
    customer_address TEXT NOT NULL,
    date_of_birth DATE,
    gender VARCHAR(20)
);

-- Create restaurants table
CREATE TABLE restaurants (
    restaurant_id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    restaurant_name VARCHAR(255) NOT NULL,
    restaurant_location TEXT NOT NULL
);

-- Create couriers table
CREATE TABLE couriers (
    courier_id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    courier_full_name VARCHAR(255) NOT NULL,
    courier_address TEXT NOT NULL,
    date_of_birth DATE,
    gender VARCHAR(20)
);

-- Create orders table with additional cost field
CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    customer_id INTEGER REFERENCES customers(customer_id),
    restaurant_id INTEGER REFERENCES restaurants(restaurant_id),
    courier_id INTEGER REFERENCES couriers(courier_id),
    order_status VARCHAR(50) NOT NULL,
    items TEXT,
    delivery_location TEXT NOT NULL,
    cost DECIMAL(10,2)
);

-- Insert sample data into customers table
INSERT INTO customers (customer_full_name, customer_address, date_of_birth, gender) VALUES
('John Smith', '123 Main St, Baghdad, Iraq', '1990-05-15', 'Male'),
('Sarah Ahmed', '456 Al-Rashid St, Baghdad, Iraq', '1985-08-22', 'Female'),
('Mohammed Ali', '789 Haifa St, Baghdad, Iraq', '1992-12-10', 'Male'),
('Fatima Hassan', '321 Karrada St, Baghdad, Iraq', '1988-03-07', 'Female'),
('Omar Khalil', '654 Mansour St, Baghdad, Iraq', '1995-09-18', 'Male');

-- Insert sample data into restaurants table
INSERT INTO restaurants (restaurant_name, restaurant_location) VALUES
('Al-Baghdadi Restaurant', '101 Commercial St, Baghdad, Iraq'),
('Pizza Palace', '202 University St, Baghdad, Iraq'),
('Shawarma Express', '303 Saadoun St, Baghdad, Iraq'),
('Burger House', '404 Tahrir St, Baghdad, Iraq'),
('Oriental Kitchen', '505 Jadiriyah St, Baghdad, Iraq');

-- Insert sample data into couriers table
INSERT INTO couriers (courier_full_name, courier_address, date_of_birth, gender) VALUES
('Ahmed Hassan', '111 Zayouna St, Baghdad, Iraq', '1993-06-12', 'Male'),
('Layla Ibrahim', '222 Adhamiyah St, Baghdad, Iraq', '1991-11-25', 'Female'),
('Karim Mustafa', '333 Karkh St, Baghdad, Iraq', '1994-02-14', 'Male'),
('Noor Salim', '444 Rusafa St, Baghdad, Iraq', '1990-07-30', 'Female'),
('Yusuf Omar', '555 Dora St, Baghdad, Iraq', '1987-04-03', 'Male');

-- Insert sample data into orders table
INSERT INTO orders (customer_id, restaurant_id, courier_id, order_status, items, delivery_location, cost) VALUES
(1, 1, 1, 'Delivered', 'Grilled Chicken, Rice, Salad', '123 Main St, Baghdad, Iraq', 25.50),
(2, 2, 2, 'Delivered', 'Large Pizza Margherita, Coke', '456 Al-Rashid St, Baghdad, Iraq', 18.75),
(3, 3, 3, 'Cancelled', 'Chicken Shawarma, Fries', '789 Haifa St, Baghdad, Iraq', 12.00),
(4, 4, 4, 'Refunded', 'Burger Combo, Milkshake', '321 Karrada St, Baghdad, Iraq', 22.25),
(5, 5, 5, 'Delivered', 'Mixed Grill, Hummus, Bread', '654 Mansour St, Baghdad, Iraq', 32.80);

-- Create indexes for better performance
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_restaurant_id ON orders(restaurant_id);
CREATE INDEX idx_orders_courier_id ON orders(courier_id);
CREATE INDEX idx_orders_status ON orders(order_status);
CREATE INDEX idx_orders_created_at ON orders(created_at);

