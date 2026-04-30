<?php
declare(strict_types=1);

// Заменяется forms.generate_send_email_php() из forms.test_recipients конфига.
const TEST_RECIPIENTS = [
    'test@example.com',
];

const STANDARD_FIELDS = [
    'Name',
    'Company',
    'Country',
    'Email',
    'Phone',
    'Message',
];

const FIELD_ALIASES = [
    'Name' => ['name', 'fullname', 'your-name'],
    'Company' => ['company', 'company_name'],
    'Country' => ['country', 'location_country'],
    'Email' => ['email', 'mail', 'your-email'],
    'Phone' => ['phone', 'tel', 'telephone'],
    'Message' => ['message', 'comment', 'text'],
];

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    respond(405, false, 'Method Not Allowed');
}

$normalized = normalize_post_data($_POST);
[$standard, $extra] = split_fields($normalized);

$name = trim((string)($standard['Name'] ?? ''));
$email = trim((string)($standard['Email'] ?? ''));
$phone = trim((string)($standard['Phone'] ?? ''));

if ($name === '') {
    respond(422, false, 'Поле Name обязательно');
}
if ($email === '' || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
    respond(422, false, 'Поле Email заполнено некорректно');
}
if ($phone !== '' && !preg_match('/^[0-9+()\-\s]+$/', $phone)) {
    respond(422, false, 'Поле Phone заполнено некорректно');
}

$domain = detect_domain_from_host();
if ($domain === null) {
    respond(500, false, 'Не удалось определить домен сайта');
}

$isTestSubmission = is_test_submission($name);
$recipients = $isTestSubmission ? TEST_RECIPIENTS : ['info@' . $domain];

$message = build_message($standard, $extra, $domain, $isTestSubmission);
$subject = encode_subject('New request from ' . $domain);

$from = safe_header_email('no-reply@' . $domain);
$replyTo = safe_header_email($email) ?: $from;

$headers = implode("\r\n", [
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'From: ' . $from,
    'Reply-To: ' . $replyTo,
]);

$sentOk = true;
foreach ($recipients as $recipient) {
    $safeRecipient = safe_header_email($recipient);
    if ($safeRecipient === '') {
        $sentOk = false;
        continue;
    }

    $current = @mail($safeRecipient, $subject, $message, $headers);
    if (!$current) {
        $sentOk = false;
    }
}

if (!$sentOk) {
    respond(500, false, 'Не удалось отправить письмо');
}

respond(200, true, 'Заявка отправлена', [
    'mode' => $isTestSubmission ? 'test' : 'main',
    'recipients' => $recipients,
]);

/**
 * @return array<string, string>
 */
function normalize_post_data(array $post): array
{
    $out = [];

    foreach ($post as $key => $value) {
        $rawKey = trim((string)$key);
        if ($rawKey === '') {
            continue;
        }

        if (is_array($value)) {
            $parts = array_map(
                static fn ($item): string => sanitize_multiline((string)$item),
                $value
            );
            $rawValue = implode(', ', $parts);
        } else {
            $rawValue = sanitize_multiline((string)$value);
        }

        $out[$rawKey] = trim($rawValue);
    }

    return $out;
}

/**
 * @param array<string, string> $data
 * @return array{0: array<string, string>, 1: array<string, string>}
 */
function split_fields(array $data): array
{
    $standard = array_fill_keys(STANDARD_FIELDS, '');
    $extra = [];

    foreach ($data as $rawKey => $value) {
        if (should_ignore_field($rawKey)) {
            continue;
        }

        $canonical = canonical_field_name($rawKey);
        if ($canonical !== null) {
            if ($standard[$canonical] === '') {
                $standard[$canonical] = $value;
            }
            continue;
        }

        $extra[sanitize_field_name($rawKey)] = $value;
    }

    return [$standard, $extra];
}

function should_ignore_field(string $key): bool
{
    $ignored = ['redirect', 'redirect2parent', 'g-recaptcha-response', 'csrf_token'];
    return in_array(mb_strtolower(trim($key)), $ignored, true);
}

function canonical_field_name(string $key): ?string
{
    $token = normalize_alias_token($key);

    foreach (FIELD_ALIASES as $canonical => $aliases) {
        foreach ($aliases as $alias) {
            if ($token === normalize_alias_token($alias)) {
                return $canonical;
            }
        }
    }

    return null;
}

function normalize_alias_token(string $value): string
{
    $value = mb_strtolower(trim($value));
    $value = preg_replace('/[\s_]+/u', '-', $value) ?? $value;
    $value = preg_replace('/[^\p{L}\p{N}\-]/u', '', $value) ?? $value;
    return trim((string)$value, '-');
}

function detect_domain_from_host(): ?string
{
    $rawHost = (string)($_SERVER['HTTP_HOST'] ?? $_SERVER['SERVER_NAME'] ?? '');
    $host = trim($rawHost);

    if ($host === '') {
        return null;
    }

    if (strpos($host, '://') !== false) {
        $parsedHost = (string)parse_url($host, PHP_URL_HOST);
        if ($parsedHost !== '') {
            $host = $parsedHost;
        }
    }

    $host = strtolower($host);
    $host = preg_replace('/:\d+$/', '', $host) ?? $host;
    $host = preg_replace('/^www\./i', '', $host) ?? $host;

    if ($host === '' || !preg_match('/^[a-z0-9.-]+$/', $host)) {
        return null;
    }

    return $host;
}

function is_test_submission(string $name): bool
{
    return preg_match('/\btest\b/i', $name) === 1;
}

/**
 * @param array<string, string> $standard
 * @param array<string, string> $extra
 */
function build_message(array $standard, array $extra, string $domain, bool $isTest): string
{
    $lines = [
        'Form submission from ' . $domain,
        'Date: ' . gmdate('Y-m-d H:i:s') . ' UTC',
        'Route: ' . ($isTest ? 'TEST_ONLY' : 'MAIN_ONLY'),
        str_repeat('-', 40),
    ];

    foreach (['Name', 'Company', 'Country', 'Email', 'Phone'] as $field) {
        if (($standard[$field] ?? '') !== '') {
            $lines[] = $field . ': ' . $standard[$field];
        }
    }

    $messageText = trim((string)($standard['Message'] ?? ''));
    $extraLines = [];
    foreach ($extra as $field => $value) {
        $extraLines[] = $field . ': ' . $value;
    }

    if ($messageText !== '') {
        $lines[] = 'Message: ' . $messageText;
    }

    if ($extraLines !== []) {
        if ($messageText === '') {
            $lines[] = 'Message:';
        }
        $lines[] = str_repeat('-', 20);
        $lines[] = 'Additional fields:';
        foreach ($extraLines as $line) {
            $lines[] = $line;
        }
    }

    return implode("\n", $lines);
}

function sanitize_multiline(string $value): string
{
    $value = str_replace(["\r\n", "\r"], "\n", $value);
    $value = str_replace("\0", '', $value);
    return trim($value);
}

function sanitize_field_name(string $field): string
{
    $field = preg_replace('/[\r\n\0]+/', ' ', $field) ?? $field;
    $field = trim($field);
    return $field !== '' ? $field : 'Field';
}

function safe_header_email(string $email): string
{
    $email = trim($email);
    if (preg_match('/[\r\n]/', $email) === 1) {
        return '';
    }

    return filter_var($email, FILTER_VALIDATE_EMAIL) ? $email : '';
}

function encode_subject(string $subject): string
{
    $subject = preg_replace('/[\r\n]+/', ' ', $subject) ?? $subject;
    return '=?UTF-8?B?' . base64_encode(trim($subject)) . '?=';
}

/**
 * @param array<string, mixed> $extra
 */
function respond(int $status, bool $ok, string $message, array $extra = []): void
{
    http_response_code($status);

    $payload = array_merge([
        'ok' => $ok,
        'message' => $message,
    ], $extra);

    $isAjax = strtolower((string)($_SERVER['HTTP_X_REQUESTED_WITH'] ?? '')) === 'xmlhttprequest';
    if ($isAjax) {
        header('Content-Type: application/json; charset=UTF-8');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        exit;
    }

    if (!$ok) {
        header('Content-Type: text/plain; charset=UTF-8');
        echo $message;
        exit;
    }

    $back = (string)($_POST['redirect'] ?? $_POST['redirect2parent'] ?? $_SERVER['HTTP_REFERER'] ?? '/');
    $backUrl = build_safe_redirect_url($back, $ok);
    header('Location: ' . $backUrl, true, 303);
    exit;
}

function build_safe_redirect_url(string $back, bool $ok): string
{
    $fallback = '/';
    $parsed = parse_url($back);
    if ($parsed === false) {
        return '/?sent=' . ($ok ? '1' : '0');
    }

    $currentHost = strtolower((string)($_SERVER['HTTP_HOST'] ?? ''));
    $currentHost = preg_replace('/:\d+$/', '', $currentHost) ?? $currentHost;
    $currentHost = preg_replace('/^www\./i', '', $currentHost) ?? $currentHost;

    if (!empty($parsed['host'])) {
        $backHost = strtolower((string)$parsed['host']);
        $backHost = preg_replace('/^www\./i', '', $backHost) ?? $backHost;
        if ($backHost !== $currentHost) {
            return $fallback . '?sent=' . ($ok ? '1' : '0');
        }
    }

    $base = $parsed['path'] ?? $fallback;
    if ($base === '') {
        $base = $fallback;
    }

    $query = $parsed['query'] ?? '';
    parse_str($query, $params);
    $params['sent'] = $ok ? '1' : '0';
    $queryOut = http_build_query($params);

    $hash = !empty($parsed['fragment']) ? '#' . $parsed['fragment'] : '#popup:myform';
    return $base . ($queryOut !== '' ? '?' . $queryOut : '') . $hash;
}
