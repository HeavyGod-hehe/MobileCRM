/** Free WhatsApp share helpers (wa.me links). */

function formatPhoneForWhatsApp(phone) {
  if (!phone) return '';
  let digits = String(phone).replace(/\D/g, '');
  if (!digits) return '';
  if (digits.startsWith('0')) digits = '92' + digits.slice(1);
  if (!digits.startsWith('92') && digits.length === 10) digits = '92' + digits;
  return digits;
}

function buildWhatsAppUrl(phone, message) {
  const num = formatPhoneForWhatsApp(phone);
  if (!num) return null;
  return `https://wa.me/${num}?text=${encodeURIComponent(message)}`;
}

function openWhatsAppShare(phone, message) {
  const url = buildWhatsAppUrl(phone, message);
  if (!url) {
    if (typeof toast === 'function') toast('Enter a valid customer phone number', 'error');
    return false;
  }
  window.open(url, '_blank', 'noopener');
  return true;
}

function buildInvoiceWhatsAppMessage(shop, invoice) {
  const lines = [
    `*${shop.shop_name || 'Shop'}*`,
    `Invoice #${invoice.invoice_number}`,
    `Date: ${invoice.invoice_date || new Date().toLocaleDateString('en-PK')}`,
    '',
  ];
  if (invoice.customer_name) lines.push(`Customer: ${invoice.customer_name}`);
  if (invoice.model) lines.push(`Phone: ${invoice.model}${invoice.variant ? ' (' + invoice.variant + ')' : ''}`);
  if (invoice.imei) lines.push(`IMEI: ${invoice.imei}`);
  if (invoice.phone_type) lines.push(`Type: ${invoice.phone_type}`);
  if (invoice.amount) lines.push(`Amount: Rs. ${Number(invoice.amount).toLocaleString('en-PK')}`);
  if (invoice.warranty) lines.push(`Warranty: ${invoice.warranty}`);
  lines.push('', 'Thank you for your purchase!');
  if (shop.shop_whatsapp) lines.push(`Contact: ${shop.shop_whatsapp}`);
  return lines.filter(Boolean).join('\n');
}

function buildBalanceWhatsAppMessage(shop, account) {
  const bal = account.balance || 0;
  let status;
  if (bal > 0) status = `You owe us *Rs. ${Math.abs(bal).toLocaleString('en-PK')}* (Udhar receivable)`;
  else if (bal < 0) status = `We owe you *Rs. ${Math.abs(bal).toLocaleString('en-PK')}*`;
  else status = 'Your account is *settled* (Rs. 0)';
  return [
    `*${shop.shop_name || 'Shop'}*`,
    `Khata — ${account.name}`,
    '',
    status,
    '',
    `As of ${new Date().toLocaleDateString('en-PK')}`,
    shop.shop_whatsapp ? `Contact: ${shop.shop_whatsapp}` : '',
  ].filter(Boolean).join('\n');
}
