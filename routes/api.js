const express = require('express');
const router = express.Router();
const validator = require('validator');
const xss = require('xss');
const { sendMatchRequestEmail } = require('../utils/mailer');

router.post('/match-request', async (req, res) => {
    let { match, email } = req.body;

    // 1. Validation
    if (!match || validator.isEmpty(match.trim())) {
        return res.status(400).json({ error: 'Match field cannot be empty.' });
    }

    if (!email || !validator.isEmail(email)) {
        return res.status(400).json({ error: 'Please provide a valid email format.' });
    }

    // 2. Sanitization
    match = xss(match.trim());
    email = validator.normalizeEmail(email);

    // 3. Metadata
    const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
    const timestamp = new Date().toLocaleString();

    try {
        // 4. Send Email
        await sendMatchRequestEmail({ match, email, ip, timestamp });

        console.log(`[${timestamp}] Match request sent for: ${match} by ${email}`);

        res.status(200).json({ message: 'Request sent successfully! We will get back to you soon.' });
    } catch (error) {
        console.error('Email Error:', error);
        res.status(500).json({ error: 'Failed to send request. Please try again later.' });
    }
});

module.exports = router;
