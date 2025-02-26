#!/usr/bin/env python3
"""Kagi Text File Translation Script.

Chops up text files, sends them to Kagi's translation API, and stitches the results back together.
Uses parallel requests to speed things up.

Usage:
  translate.py <input_file> <output_file> --to=<target_lang> [options]

Options:
  -h --help                    Show this help
  --from=<source_lang>         Source language [default: Automatic]
  --to=<target_lang>           Target language (required)
  --token=<api_key>            Your Kagi API token 
  --endpoint=<url>             API endpoint [default: https://translate.kagi.com/?/translate]
  --max-length=<chars>         Max chars per chunk [default: 1500]
  --max-requests=<num>         Max chunks to process [default: 100]
  --workers=<num>              Parallel workers [default: 3]
  --verbose                    Show detailed progress

Example:
  translate.py --to=Polish --token=<your_token_here> --workers=5 input.txt output.txt 
"""

import os
import json
import requests
import random
import time
from urllib.parse import urlencode
from docopt import docopt
from concurrent.futures import ThreadPoolExecutor, as_completed

def split_text_into_chunks(text, max_length):
    """chop text into manageable chunks."""
    chunks = []
    current_chunk = ""
    
    for line in text.split('\n'):
        # If this line would push us over the limit, save and start new chunk
        if len(current_chunk) + len(line) + 1 > max_length and current_chunk:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            # Add newline if needed
            if current_chunk:
                current_chunk += '\n'
            current_chunk += line
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

def translate_chunk(args):
    """send a single chunk to Kagi for translation."""
    chunk, from_lang, to_lang, token, endpoint, verbose, chunk_idx = args
    
    # add little delay to avoid rate limits
    time.sleep(random.uniform(0.1, 0.5))
    
    payload = {
        "from": from_lang,
        "to": to_lang,
        "text": chunk
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": token,
        "Accept": "application/json"
    }
    
    # Setup auth with cookie
    session = requests.Session()
    session.cookies.set(
        name="kagi_session",
        value=token,
        domain=".kagi.com",
        path="/",
        secure=True
    )
    
    tries = 0
    max_tries = 3
    
    while tries < max_tries:
        try:
            if verbose:
                print(f"Chunk {chunk_idx+1}: Sending {len(chunk)} chars...", end="", flush=True)
            
            response = session.post(
                endpoint,
                headers=headers,
                data=urlencode(payload)
            )
            
            # handle rate limiting
            if response.status_code == 429:
                wait_time = 5 + random.uniform(tries * 2, tries * 4)
                if verbose:
                    print(f" Rate limited! Backing off for {wait_time:.1f}s")
                time.sleep(wait_time)
                tries += 1
                continue
                
            if not response.ok:
                if verbose:
                    print(f" Failed! Status {response.status_code}")
                return (chunk_idx, None)
            
            data = response.json()
            translated_text = json.loads(data["data"])[2]
            
            if verbose:
                print(f" Done! ({len(translated_text)} chars)")
                
            return (chunk_idx, translated_text)
        
        except Exception as e:
            tries += 1
            if verbose:
                print(f"\nError on chunk {chunk_idx+1}: {str(e)}")
            if tries < max_tries:
                time.sleep(2 * tries)  # backoff ;/
            else:
                return (chunk_idx, None)

def translate_file(input_file_path, output_file_path, from_lang, to_lang, token, endpoint, 
                   max_length, max_requests, workers, verbose=False):
    """Do the actual translation work."""
    try:
        # Read the file
        with open(input_file_path, 'r', encoding='utf-8') as file:
            text = file.read()
        
        if verbose:
            print(f"Loaded {len(text)} chars from {input_file_path}")
        
        chunks = split_text_into_chunks(text, max_length)
        if max_requests > 0:
            chunks = chunks[:max_requests]  # Limit if needed
        
        if verbose:
            print(f"Split into {len(chunks)} chunks (max size: {max_length})")
        
        translated_chunks = [None] * len(chunks)
        
        chunk_args = [
            (chunk, from_lang, to_lang, token, endpoint, verbose, i)
            for i, chunk in enumerate(chunks)
        ]
        
        # translate in parallel
        print(f"starting translation with {workers} workers...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(translate_chunk, args) for args in chunk_args]
            
            for future in as_completed(futures):
                idx, result = future.result()
                if result:
                    translated_chunks[idx] = result
                else:
                    print(f"❌ chunk {idx+1} failed - output will have gaps")
        
        # combine and save <3
        translated_text = '\n'.join([chunk for chunk in translated_chunks if chunk])
        
        with open(output_file_path, 'w', encoding='utf-8') as file:
            file.write(translated_text)
        
        print(f"done! output saved to {output_file_path}")
    
    except Exception as e:
        print(f"Error: {str(e)}")

def main():
    arguments = docopt(__doc__)
    
    input_file = arguments['<input_file>']
    output_file = arguments['<output_file>']
    from_lang = arguments['--from']
    to_lang = arguments['--to']
    token = arguments['--token']
    endpoint = arguments['--endpoint']
    max_length = int(arguments['--max-length'])
    max_requests = int(arguments['--max-requests'])
    workers = int(arguments['--workers'])
    verbose = arguments['--verbose']
    
    if not token:
        token = os.environ.get('KAGI_TOKEN', '')
        if not token:
            print("no API token! provide --token or set KAGI_TOKEN in your env")
            return
    
    translate_file(input_file, output_file, from_lang, to_lang, token, endpoint, 
                   max_length, max_requests, workers, verbose)



if __name__ == "__main__":
    main()
