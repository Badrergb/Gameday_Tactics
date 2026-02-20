const nodemailer = require('nodemailer');
require('dotenv').config();

const transporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: process.env.SMTP_PORT,
    secure: process.env.SMTP_PORT == 465, // true for 465, false for other ports
    auth: {
        user: process.env.SMTP_USER,
        pass: process.env.SMTP_PASS,
    },
});

/**
 * Sends a match request email.
 * @param {Object} details - The match request details.
 * @param {string} details.match - The requested match name.
 * @param {string} details.email - The user's email address.
 * @param {string} details.ip - The user's IP address.
 * @param {string} details.timestamp - The time of the request.
 */
const sendMatchRequestEmail = async ({ match, email, ip, timestamp }) => {
    const mailOptions = {
        from: `"${process.env.SMTP_USER}" <${process.env.SMTP_USER}>`, // Authenticated sender
        to: process.env.ADMIN_EMAIL,
        replyTo: email, // Set replyTo to user's email
        subject: `New Match Request: ${match}`,
        text: `New match requested.\n\nMatch: ${match}\nRequested By: ${email}\nTime: ${timestamp}\nIP: ${ip}\n\nReply directly to this email to respond to the user.`,
        html: `
            <h3>New match requested.</h3>
            <p><strong>Match:</strong> ${match}</p>
            <p><strong>Requested By:</strong> ${email}</p>
            <p><strong>Time:</strong> ${timestamp}</p>
            <p><strong>IP:</strong> ${ip}</p>
            <p><em>Reply directly to this email to respond to the user.</em></p>
        `,
    };

    return transporter.sendMail(mailOptions);
};

module.exports = {
    sendMatchRequestEmail,
};
