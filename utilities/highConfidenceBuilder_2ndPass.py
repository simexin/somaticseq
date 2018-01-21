#!/usr/bin/env python3

import sys, argparse, math, gzip, os, re, copy

MY_DIR = os.path.dirname(os.path.realpath(__file__))
PRE_DIR = os.path.join(MY_DIR, os.pardir)
sys.path.append( PRE_DIR )

import genomic_file_handlers as genome

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-vcfin',    '--vcf-infile', type=str, help='VCF in', required=True)
parser.add_argument('-tsvin',    '--tsv-infile', type=str, help='TSV in', required=True)
parser.add_argument('-outfile',  '--outfile',    type=str, help='VCF out', required=True)
parser.add_argument('-pass',     '--pass-score',   type=float, help='PASS SCORE. Default=phred scaled 0.7',    required=False, default=5.228787452803376)
parser.add_argument('-reject',   '--reject-score', type=float, help='REJECT SCORE. Default=phred scaled 0.1',  required=False, default=0.4575749056067512)
parser.add_argument('-ncallers', '--num-callers',  type=int,   help='# callers to be considered PASS if untrained', required=False, default=3)

args = parser.parse_args()

vcfin          = args.vcf_infile
tsvin          = args.tsv_infile
outfile        = args.outfile
pass_score     = args.pass_score
reject_score   = args.reject_score
ncallers       = args.num_callers

def all_indices(pattern_to_be_matched, my_list):
    return [ i for i,j in enumerate(my_list) if j == pattern_to_be_matched ]


with genome.open_textfile(vcfin) as vcf_in,  genome.open_textfile(tsvin) as tsv_in,  open(outfile, 'w') as vcfout:
    
    vcf_line = vcf_in.readline().rstrip()
    tsv_line = tsv_in.readline().rstrip()
    
    # GO THRU THE VCF HEADER
    while vcf_line.startswith('##'):
        vcfout.write( vcf_line + '\n' )
        vcf_line = vcf_in.readline().rstrip()
        
    vcfout.write('##INFO=<ID=VERDICT,Number=.,Type=String,Description="Reasons for PASS, LowQual, or REJECT">\n')
    vcfout.write( vcf_line + '\n' )
    
    vcf_header = vcf_line.split('\t')
    samples    = vcf_header[9::]
    
    bwa_tumors    = []
    bowtie_tumors = []
    novo_tumors   = []
    
    for sample_i in samples:
        if   sample_i.endswith('.bwa'):
            bwa_tumors.append( sample_i )
        elif sample_i.endswith('.bowtie'):
            bowtie_tumors.append( sample_i )
        elif sample_i.endswith('.novo'):
            novo_tumors.append( sample_i )
    
    bwa_tumor_indices     = [ samples.index(i) for i in bwa_tumors     ]
    bowtie_tumor_indices  = [ samples.index(i) for i in bowtie_tumors  ]
    novo_tumor_indices    = [ samples.index(i) for i in novo_tumors    ]
    
    bwa_normal_index    = samples.index('combined_bwa_normals')
    bowtie_normal_index = samples.index('combined_bowtie_normals')
    novo_normal_index   = samples.index('combined_novo_normals')
    
    # GO THRU THE 1 TSV HEADER LINE
    tsv_headers = tsv_line.split('\t')
    i_tsv_chr = tsv_headers.index('CHROM')
    i_tsv_pos = tsv_headers.index('POS')
    i_tsv_ref = tsv_headers.index('REF')
    i_tsv_alt = tsv_headers.index('ALT')
    
    vcf_line = vcf_in.readline().rstrip()
    tsv_line = tsv_in.readline().rstrip()
    
    while vcf_line:
        
        # VCF
        vcf_i = genome.Vcf_line( vcf_line )
        sample_columns = vcf_line.split('\t')[9::]
        
        # TSV
        tsv_items = tsv_line.split('\t')
        
        # Make sure we're on the same line
        assert (tsv_items[i_tsv_chr], tsv_items[i_tsv_pos], tsv_items[i_tsv_ref], tsv_items[i_tsv_alt]) == (vcf_i.chromosome, str(vcf_i.position), vcf_i.refbase, vcf_i.altbase)

        # Tiering
        if vcf_i.filters == 'AllPASS':
            vcfout.write( vcf_line + '\n' )
            
        elif vcf_i.filters == 'Tier1':
            
            nREJECTS = int( vcf_i.get_info_value('nREJECTS') )
            nNoCall  = int( vcf_i.get_info_value('nNoCall') )
            
            # Get called samples stats (would by pass if no REJECT or NoCall)
            # Try to find reasons for REJECTS
            if nREJECTS > 0:
                
                # Get the samples that give REJECT calls:
                rejects = vcf_i.get_info_value('rejectedSamples').split(',')
                
                # Is it aligner-specific?
                rejected_aligners       = []
                rejected_variant_depths = []
                rejected_tbq            = []
                rejected_tmq            = []
                rejected_tnm            = [] 
                rejected_mq0            = []
                rejected_poors          = []
                rejected_others         = []
                rejected_sor            = []
                
                for sample_i in rejects:
                    
                    matched_normal_i = re.sub('_T_',  '_N_', sample_i)
                    
                    i_alt_for = tsv_headers.index( sample_i+'_bam_ALT_FOR' )
                    i_alt_rev = tsv_headers.index( sample_i+'_bam_ALT_REV' )
                    i_tbq     = tsv_headers.index( sample_i+'_bam_ALT_BQ' )
                    i_tmq     = tsv_headers.index( sample_i+'_bam_ALT_MQ' )
                    i_tnm     = tsv_headers.index( sample_i+'_bam_ALT_NM' )
                    i_mq0     = tsv_headers.index( sample_i+'_bam_MQ0' )
                    i_poors   = tsv_headers.index( sample_i+'_bam_Poor_Reads' )
                    i_others  = tsv_headers.index( sample_i+'_bam_Poor_Reads' )
                    i_sor     = tsv_headers.index( sample_i+'.'+matched_normal_i+'_bam_ALT_NM' )
                    
                    if   sample_i.endswith('.bwa'):
                        rejected_aligners.append('bwa')
                    elif sample_i.endswith('.bowtie'):
                        rejected_aligners.append('bowtie')
                    elif sample_i.endswith('.novo'):
                        rejected_aligners.append('novo')

                    rejected_variant_depths.append( int(tsv_items[i_alt_for]) + int(tsv_items[i_alt_rev]) )
                    rejected_tbp.append(    int(tsv_items[i_tbq]    )
                    rejected_tmq.append(    int(tsv_items[i_tmq]    )
                    rejected_tnm.append(    int(tsv_items[i_tnm]    )
                    rejected_mq0.append(    int(tsv_items[i_mq0]    )
                    rejected_poors.append(  int(tsv_items[i_poors]  )
                    rejected_others.append( int(tsv_items[i_others] )
                    rejected_sor.append(    int(tsv_items[i_sor]    )
                    
            
            # Try to find reasons for missing call altogether
            if nNoCall > 0:
                pass


            # Extract stats from called samples so they can be a baseline for comparison
            if nREJECTS or nNoCall:
                called = vcf_i.get_info_value('calledSamples').split(',')
                
                called_aligners       = []
                called_variant_depths = []
                called_tbq            = []
                called_tmq            = []
                called_tnm            = [] 
                called_mq0            = []
                called_poors          = []
                called_others         = []
                called_sor            = []
                
                for sample_i in rejects:
                    
                    matched_normal_i = re.sub('_T_',  '_N_', sample_i)
                    
                    i_alt_for = tsv_headers.index( sample_i+'_bam_ALT_FOR' )
                    i_alt_rev = tsv_headers.index( sample_i+'_bam_ALT_REV' )
                    i_tbq     = tsv_headers.index( sample_i+'_bam_ALT_BQ' )
                    i_tmq     = tsv_headers.index( sample_i+'_bam_ALT_MQ' )
                    i_tnm     = tsv_headers.index( sample_i+'_bam_ALT_NM' )
                    i_mq0     = tsv_headers.index( sample_i+'_bam_MQ0' )
                    i_poors   = tsv_headers.index( sample_i+'_bam_Poor_Reads' )
                    i_others  = tsv_headers.index( sample_i+'_bam_Poor_Reads' )
                    i_sor     = tsv_headers.index( sample_i+'.'+matched_normal_i+'_bam_ALT_NM' )
                    
                    if   sample_i.endswith('.bwa'):
                        called_aligners.append('bwa')
                    elif sample_i.endswith('.bowtie'):
                        called_aligners.append('bowtie')
                    elif sample_i.endswith('.novo'):
                        called_aligners.append('novo')

                    called_variant_depths.append( int(tsv_items[i_alt_for]) + int(tsv_items[i_alt_rev]) )
                    called_tbp.append(    int(tsv_items[i_tbq]    )
                    called_tmq.append(    int(tsv_items[i_tmq]    )
                    called_tnm.append(    int(tsv_items[i_tnm]    )
                    called_mq0.append(    int(tsv_items[i_mq0]    )
                    called_poors.append(  int(tsv_items[i_poors]  )
                    called_others.append( int(tsv_items[i_others] )
                    called_sor.append(    int(tsv_items[i_sor]    )
                    
            



        
        vcf_line = vcf_in.readline().rstrip()
        tsv_line = tsv_in.readline().rstrip()