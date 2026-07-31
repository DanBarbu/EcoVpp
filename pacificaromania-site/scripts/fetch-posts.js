#!/usr/bin/env node
// Fetches latest posts from Facebook Graph API and rebuilds the posts section in index.html

const https = require('https');
const fs = require('fs');
const path = require('path');

const PAGE_ID    = process.env.FB_PAGE_ID    || '61574158391297';
const PAGE_TOKEN = process.env.FB_PAGE_TOKEN;

if (!PAGE_TOKEN) {
  console.error('ERROR: FB_PAGE_TOKEN environment variable is not set.');
  process.exit(1);
}

const FIELDS = 'message,full_picture,created_time,permalink_url,attachments';
const LIMIT  = 10;
const API_URL = `https://graph.facebook.com/v19.0/${PAGE_ID}/posts?fields=${FIELDS}&limit=${LIMIT}&access_token=${PAGE_TOKEN}`;

function get(url) {
  return new Promise((resolve, reject) => {
    https.get(url, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { year: 'numeric', month: 'long', day: 'numeric' });
}

function escapeHtml(str) {
  return (str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/\n/g, '<br>');
}

function buildPostCard(post) {
  const date    = formatDate(post.created_time);
  const message = escapeHtml(post.message || '');
  const image   = post.full_picture
    ? `<div class="post-img"><img src="${post.full_picture}" alt="Post image" loading="lazy"></div>`
    : '';
  const link    = post.permalink_url || `https://www.facebook.com/${PAGE_ID}`;

  return `
        <div class="post-card dyn-post">
          ${image}
          <div class="post-body">
            <p class="post-date">${date}</p>
            <p class="post-text">${message}</p>
            <a href="${link}" target="_blank" rel="noopener" class="post-link"
               data-en="Read on Facebook" data-ro="Citește pe Facebook">Read on Facebook</a>
          </div>
        </div>`;
}

function buildPostsHTML(posts) {
  if (!posts || posts.length === 0) {
    return `<p class="no-posts" data-en="No posts yet." data-ro="Nicio postare încă.">No posts yet.</p>`;
  }
  return posts.map(buildPostCard).join('\n');
}

async function main() {
  console.log('Fetching posts from Facebook Graph API...');

  let data;
  try {
    data = await get(API_URL);
  } catch (err) {
    console.error('Network error:', err.message);
    process.exit(1);
  }

  if (data.error) {
    console.error('Facebook API error:', JSON.stringify(data.error, null, 2));
    process.exit(1);
  }

  const posts = (data.data || []).filter(p => p.message);
  console.log(`Fetched ${posts.length} posts.`);

  const postsHTML = buildPostsHTML(posts);

  const indexPath = path.join(__dirname, '..', 'index.html');
  let html = fs.readFileSync(indexPath, 'utf8');

  // Replace everything between the markers
  const START = '<!-- POSTS:START -->';
  const END   = '<!-- POSTS:END -->';
  const startIdx = html.indexOf(START);
  const endIdx   = html.indexOf(END);

  if (startIdx === -1 || endIdx === -1) {
    console.error('Markers <!-- POSTS:START --> and <!-- POSTS:END --> not found in index.html');
    process.exit(1);
  }

  const updated = html.slice(0, startIdx + START.length)
    + '\n' + postsHTML + '\n      '
    + html.slice(endIdx);

  fs.writeFileSync(indexPath, updated, 'utf8');
  console.log('index.html updated successfully.');
}

main();
