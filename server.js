const express = require('express');
const cors = require('cors');
const rateLimit = require('express-rate-limit');
const dotenv = require('dotenv');
const apiRoutes = require('./routes/api');

// Initialize environment variables
dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

// Security Middleware
app.use(cors()); // Enable CORS if frontend is on a different port
app.use(express.json()); // Body parser

// Rate Limiting: Prevent spam
const limiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 10, // Limit each IP to 10 requests per window
    message: { error: 'Too many requests from this IP, please try again after 15 minutes.' },
    standardHeaders: true,
    legacyHeaders: false,
});

app.use('/api/', limiter);

// Routes
app.use('/api', apiRoutes);

// Health Check
app.get('/health', (req, res) => res.status(200).send('OK'));

// Start Server
app.listen(PORT, () => {
    console.log(`🚀 Match Request Server running on port ${PORT}`);
});
