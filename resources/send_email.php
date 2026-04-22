<?php
declare(strict_types=1);

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(405);
    header('Content-Type: text/plain; charset=UTF-8');
    echo 'Method Not Allowed';
    exit;
}

const TEST_RECIPIENTS = [
    'r@prororo.com',
    '3362768@mail.ru',
    'ivan3362768@gmail.com',
];

/** @return non-empty-string */
function detect_domain_from_host(): string
{
    $rawHost = (string)($_SERVER['HTTP_HOST'] ?? $_SERVER['SERVER_NAME'] ?? '');
    $host = strtolower(trim($rawHost));

    if ($host === '') {
        return 'localhost';
    }

    if (strpos($host, '://') !== false) {
        $parsedHost = (string)parse_url($host, PHP_URL_HOST);
        if ($parsedHost !== '') {
            $host = $parsedHost;
        }
    }

    $host = preg_replace('/:\\d+$/', '', $host) ?? $host;
    $host = preg_replace('/^www\./i', '', $host) ?? $host;

    return $host !== '' ? $host : 'localhost';
}

function form_value(string $key, string $default = ''): string
{
    if (!isset($_POST[$key])) {
        return $default;
    }

    $value = $_POST[$key];
    if (is_array($value)) {
        $value = implode(', ', array_map(static fn ($item): string => trim((string)$item), $value));
    }

    return trim((string)$value);
}

function is_test_submission(string $name): bool
{
    return $name !== '' && preg_match('/\btest\b/i', $name) === 1;
}

$domain = detect_domain_from_host();
$mainRecipient = 'info@' . $domain;

$name = form_value('name', form_value('Name', ''));
$email = form_value('email', form_value('Email', ''));

$isTestSubmission = is_test_submission($name);
$recipients = $isTestSubmission ? TEST_RECIPIENTS : [$mainRecipient];

$ignoredFields = ['redirect', 'redirect2parent', 'g-recaptcha-response', 'csrf_token'];
$messageLines = [
    'Form submission from ' . $domain,
    'Date: ' . date('Y-m-d H:i:s'),
    'Route: ' . ($isTestSubmission ? 'TEST_ONLY' : 'MAIN_ONLY'),
    str_repeat('-', 40),
];

foreach ($_POST as $key => $value) {
    if (in_array($key, $ignoredFields, true)) {
        continue;
    }

    if (is_array($value)) {
        $value = implode(', ', array_map('strval', $value));
    }

    $messageLines[] = $key . ': ' . trim((string)$value);
}

$messageLines[] = str_repeat('-', 40);
$message = implode("\n", $messageLines);

$subject = 'New request from ' . $domain;
$encodedSubject = '=?UTF-8?B?' . base64_encode($subject) . '?=';
$fromAddress = 'no-reply@' . $domain;
$replyTo = filter_var($email, FILTER_VALIDATE_EMAIL) ? $email : $fromAddress;

$headers = implode("\r\n", [
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'From: ' . $fromAddress,
    'Reply-To: ' . $replyTo,
]);

if (function_exists('error_clear_last')) {
    error_clear_last();
}

$sentOk = true;
foreach ($recipients as $recipient) {
    $sentCurrent = @mail($recipient, $encodedSubject, $message, $headers);
    if (!$sentCurrent) {
        $sentOk = false;
    }
}

$logTime = date('Y-m-d H:i:s');
if ($sentOk) {
    error_log(sprintf('{%s}{%s}{%s}', $logTime, implode(',', $recipients), $message));
} else {
    $lastError = error_get_last();
    $reason = isset($lastError['message']) ? (string)$lastError['message'] : 'Unknown error';
    error_log(sprintf('{%s}{%s}{%s}', $logTime, 'Ошибка', $reason));
}

$back = !empty($_POST['redirect'])
    ? (string)$_POST['redirect']
    : (!empty($_POST['redirect2parent'])
        ? (string)$_POST['redirect2parent']
        : (string)($_SERVER['HTTP_REFERER'] ?? '/'));

$parsedBack = parse_url($back);
$currentHost = strtolower((string)($_SERVER['HTTP_HOST'] ?? ''));
$currentHost = preg_replace('/:\\d+$/', '', $currentHost) ?? $currentHost;
$currentHost = preg_replace('/^www\./i', '', $currentHost) ?? $currentHost;

if (isset($parsedBack['host']) && $parsedBack['host'] !== '') {
    $backHost = strtolower((string)$parsedBack['host']);
    $backHost = preg_replace('/^www\./i', '', $backHost) ?? $backHost;

    if ($backHost !== $currentHost) {
        $back = '/';
    }
}

$hash = '#popup:myform';
if (strpos($back, '#') !== false) {
    [$base, $fragment] = explode('#', $back, 2);
    $back = $base;
    $hash = '#' . $fragment;
}

$separator = (strpos($back, '?') === false) ? '?' : '&';
$back = $back . $separator . 'sent=' . ($sentOk ? '1' : '0') . $hash;

header('Location: ' . $back, true, 303);
exit;
