const nodemailer = require('nodemailer');

function getTransporter() {
  return nodemailer.createTransport({
    host: process.env.SMTP_SERVER || 'smtp.gmail.com',
    port: parseInt(process.env.SMTP_PORT || '587'),
    secure: false,
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASSWORD,
    },
  });
}

async function sendVerificationEmail(toEmail, verifyUrl) {
  if (!process.env.SMTP_USER || !process.env.SMTP_PASSWORD) {
    console.log(`[Email] SMTP not configured. Verification URL: ${verifyUrl}`);
    return;
  }
  const transporter = getTransporter();
  await transporter.sendMail({
    from: `"Beyond The Classroom" <${process.env.SMTP_USER}>`,
    to: toEmail,
    subject: 'Verify your BTC account',
    html: `
      <div style="font-family:sans-serif;max-width:520px;margin:auto;background:#05060f;color:#f0f0f8;border-radius:16px;padding:32px;">
        <div style="text-align:center;margin-bottom:24px;">
          <div style="display:inline-block;background:linear-gradient(135deg,#137a13,#1aaa1a);border-radius:14px;padding:14px 20px;font-size:1.5rem;font-weight:800;color:white;letter-spacing:1px;">BTC</div>
        </div>
        <h2 style="color:#1aaa1a;margin-bottom:8px;">Welcome to Beyond The Classroom!</h2>
        <p style="color:#aaa;margin-bottom:24px;">You're almost there. Click the button below to verify your email address and activate your account.</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="${verifyUrl}" style="display:inline-block;background:linear-gradient(135deg,#137a13,#1aaa1a);color:white;padding:14px 32px;border-radius:10px;text-decoration:none;font-weight:700;font-size:1rem;letter-spacing:0.5px;">Verify My Email</a>
        </div>
        <p style="color:#666;font-size:0.85rem;">This link expires in 24 hours. If you didn't create a BTC account, you can safely ignore this email.</p>
        <hr style="border:none;border-top:1px solid #1a1a2e;margin:24px 0;">
        <p style="color:#444;font-size:0.8rem;text-align:center;">Beyond The Classroom — Nigerian CBT Exam Prep</p>
      </div>
    `,
  });
  console.log(`[Email] Verification sent to ${toEmail}`);
}

module.exports = { sendVerificationEmail };
