from __future__ import print_function
from __future__ import division

import subprocess
import sys
import os
import re
import random
import argparse




def main():
    '''
    If this script is run on its own, execution starts here.
    '''
    args = get_arguments()
    temp_dir_exist_at_start = os.path.exists(args.temp_dir)
    if not temp_dir_exist_at_start:
        os.makedirs(args.temp_dir)

    semi_global_align_long_reads(args.ref, args.reads, args.sam_raw, args.sam_filtered,
                                 args.temp_dir, args.graphmap_path)
    write_reference_errors_to_table(args.ref, args.reads, args.err_table_out)

    if not temp_dir_exist_at_start:
        os.rmdir(args.temp_dir)
    sys.exit(0)


def get_arguments():
    '''Specifies the command line arguments required by the script.'''
    parser = argparse.ArgumentParser(description='Semi-global long read aligner')
    parser.add_argument('--ref', type=str, required=True,
                        help='FASTA file containing one or more reference sequences')
    parser.add_argument('--reads', type=str, required=True,
                        help='FASTQ file of long reads')
    parser.add_argument('--sam_raw', type=str, required=False,
                        help='SAM file of GraphMap alignments')
    parser.add_argument('--sam_filtered', type=str, required=True,
                        help='SAM file of alignments after QC filtering')
    parser.add_argument('--err_table_out', type=str, required=False,
                        help='Table file summarising errors in the reference')
    parser.add_argument('--temp_dir', type=str, required=False, default='read_align_temp',
                        help='Temporary directory for working files')
    parser.add_argument('--graphmap_path', type=str, required=False, default='graphmap',
                        help='Path to the GraphMap executable')
    return parser.parse_args()


def semi_global_align_long_reads(ref_fasta, long_reads_fastq, sam_raw, sam_filtered, temp_dir,
                                 graphmap_path):
    '''
    This function does the primary work of this module: aligning long reads to references in an
    end-gap-free, semi-global manner. It returns a list of LongRead objects which contain their
    alignments.
    '''
    long_reads = load_long_reads(long_reads_fastq)

    if not sam_raw:
        temp_sam_raw = True
        sam_raw = os.path.join(temp_dir, 'alignments.sam')
    else:
        temp_sam_raw = False

    seq_by_seq_graphmap_alignment(ref_fasta, long_reads_fastq, sam_raw, graphmap_path, temp_dir)
    quit()
    alignments = load_alignments(sam_raw, ref_fasta)
    for alignment in alignments:
        long_reads[alignment.read_name].alignments.append(alignment)

    # Filter the alignments based on conflicting read position.
    filtered_alignments = []
    for read in long_reads.itervalues():
        read.remove_conflicting_alignments()
        filtered_alignments += read.alignments

    # Filter the alignments based on identity.
    mean_id, std_dev_id = get_mean_and_st_dev_identity(filtered_alignments)
    low_id_cutoff = mean_id - (3.0 * std_dev_id)
    filtered_alignments = []
    for read in long_reads.itervalues():
        read.remove_low_id_alignments(low_id_cutoff)
        filtered_alignments += read.alignments

    # FUTURE POSSIBILITY: FOR ANY READS WHICH ARE LACKING MAPPED REGIONS, TRY AGAIN WITH A MORE
    # SENSITIVE SEARCH.

    write_sam_file(filtered_alignments, sam_filtered)
    if temp_sam_raw:
        os.remove(sam_raw)

    return long_reads

def write_reference_errors_to_table(ref_fasta, long_reads_fastq, table_file):
    '''
    Writes a table file summarising the alignment errors in terms of reference sequence position.
    '''
    # TO DO
    # TO DO
    # TO DO
    # TO DO
    # TO DO
    # TO DO
    # TO DO
    # TO DO
    # TO DO
    # TO DO


def load_long_reads(fastq_filename):
    '''
    This function loads in long reads from a FASTQ file and returns a dictionary where key = read
    name and value = LongRead object.
    '''
    reads = {}
    fastq = open(fastq_filename, 'r')
    for line in fastq:
        name = line.strip()[1:]
        sequence = next(fastq).strip()
        _ = next(fastq)
        qualities = next(fastq).strip()
        reads[name] = LongRead(name, sequence, qualities)
    fastq.close()
    return reads

def seq_by_seq_graphmap_alignment(ref_fasta, long_reads_fastq, sam_file, graphmap_path,
                                  working_dir):
    '''
    This function runs GraphMap separately for each individual sequence in the reference.
    Resulting alignments are collected in a single SAM file.
    '''
    final_sam = open(sam_file, 'w')

    ref_headers_and_seqs = load_fasta(ref_fasta)

    for header, seq in ref_headers_and_seqs:
        nice_header = get_nice_header(header)
        one_seq_fasta = os.path.join(working_dir, nice_header + '.fasta')
        save_to_fasta(nice_header, seq, one_seq_fasta)
        sam_filename = os.path.join(working_dir, nice_header + '.sam')
        run_graphmap(one_seq_fasta, long_reads_fastq, sam_filename, graphmap_path)

        # Copy the segment's SAM alignments to the final SAM file.
        one_seq_sam = open(sam_filename, 'r')
        for line in one_seq_sam:
            if not line.startswith('@') and line.split('\t', 3)[2] != '*':
                final_sam.write(line)
        one_seq_sam.close()

        # Clean up
        os.remove(one_seq_fasta)
        os.remove(sam_filename)

    final_sam.close()

def run_graphmap(fasta, long_reads_fastq, sam_file, graphmap_path):
    '''
    This function runs GraphMap for the given inputs and produces a SAM file at the given location.
    '''
    command = [graphmap_path, '-r', fasta, '-d', long_reads_fastq, '-o',
               sam_file, '-Z', '-F', '1.0', '-t', '8', '-a', 'anchorgotoh']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, _ = process.communicate()

    # Clean up.
    os.remove(fasta + '.gmidx')
    os.remove(fasta + '.gmidxsec')

def load_alignments(sam_filename, ref_fasta):
    '''
    This function returns a list of Alignment objects from the given SAM file.
    '''
    references = {get_nice_header(header): seq for header, seq in load_fasta(ref_fasta)}
    alignments = []
    sam_file = open(sam_filename, 'r')
    for line in sam_file:
        if not line.startswith('@') and line.split('\t', 3)[2] != '*':
            alignments.append(Alignment(line.strip(), references))
    return alignments

def get_ref_shift_from_cigar_part(cigar_part):
    '''
    This function returns how much a given cigar moves on a reference.
    Examples:
      * '5M' returns 5
      * '5S' returns 0
      * '5D' returns 5
      * '5I' returns 0
    '''
    if cigar_part[-1] == 'M':
        return int(cigar_part[:-1])
    if cigar_part[-1] == 'D':
        return int(cigar_part[:-1])
    if cigar_part[-1] == 'S':
        return 0
    if cigar_part[-1] == 'I':
        return 0


def simplify_ranges(ranges):
    '''
    Collapses overlapping ranges together.
    '''
    fixed_ranges = []
    for int_range in ranges:
        if int_range[0] > int_range[1]:
            fixed_ranges.append((int_range[1], int_range[0]))
        elif int_range[0] < int_range[1]:
            fixed_ranges.append(int_range)
    starts_ends = [(x[0], 1) for x in fixed_ranges]
    starts_ends += [(x[1], -1) for x in fixed_ranges]
    starts_ends.sort(key=lambda x: x[0])
    current_sum = 0
    cumulative_sum = []
    for start_end in starts_ends:
        current_sum += start_end[1]
        cumulative_sum.append((start_end[0], current_sum))
    prev_depth = 0
    start = 0
    combined = []
    for pos, depth in cumulative_sum:
        if prev_depth == 0:
            start = pos
        elif depth == 0:
            combined.append((start, pos))
        prev_depth = depth
    return combined

def range_is_contained(test_range, other_ranges):
    '''
    Returns True if test_range is entirely contained within any range in other_ranges.
    '''
    start, end = test_range
    for other_range in other_ranges:
        if other_range[0] <= start and other_range[1] >= end:
            return True
    return False


def write_sam_file(alignments, sam_filename):
    '''
    Writes the given alignments to a SAM file.
    '''
    sam_file = open(sam_filename, 'w')
    for alignment in alignments:
        sam_file.write(alignment.get_sam_line())
        sam_file.write('\n')
    sam_file.close()


def load_fasta(filename): # type: (str) -> list[tuple[str, str]]
    '''
    Returns the names and sequences for the given fasta file.
    '''
    fasta_seqs = []
    fasta_file = open(filename, 'r')
    name = ''
    sequence = ''
    for line in fasta_file:
        line = line.strip()
        if not line:
            continue
        if line[0] == '>': # Header line = start of new contig
            if name:
                fasta_seqs.append((name.split()[0], sequence))
                name = ''
                sequence = ''
            name = line[1:]
        else:
            sequence += line
    if name:
        fasta_seqs.append((name.split()[0], sequence))
    return fasta_seqs

def is_header_spades_format(contig_name):
    '''
    Returns whether or not the header appears to be in the SPAdes/Velvet format.
    Example: NODE_5_length_150905_cov_4.42519
    '''
    contig_name_parts = contig_name.split('_')
    return len(contig_name_parts) > 5 and \
           (contig_name_parts[0] == 'NODE' or contig_name_parts[0] == 'EDGE') and \
           contig_name_parts[2] == 'length' and contig_name_parts[4] == 'cov'

def get_nice_header(header):
    '''
    For a header with a SPAdes/Velvet format, this function returns a simplified string that is
    just NODE_XX where XX is the contig number.
    For any other format, this function trims off everything following the first whitespace.
    '''
    if is_header_spades_format(header):
        return 'NODE_' + header.split('_')[1]
    else:
        return header.split()[0]

def save_to_fasta(header, sequence, filename):
    '''
    Saves the header/sequence to FASTA file.
    '''
    fasta = open(filename, 'w')
    fasta.write('>' + header + '\n')
    fasta.write(add_line_breaks_to_sequence(sequence, 60))
    fasta.close()

def save_reads_to_fastq(reads, fastq_filename):
    '''
    Writes the given reads to a FASTQ file.
    '''
    fastq = open(fastq_filename, 'w')
    for read in reads:
        fastq.write(read.get_fastq())


def add_line_breaks_to_sequence(sequence, length):
    '''
    Wraps sequences to the defined length.  All resulting sequences end in a line break.
    '''
    seq_with_breaks = ''
    while len(sequence) > length:
        seq_with_breaks += sequence[:length] + '\n'
        sequence = sequence[length:]
    if len(sequence) > 0:
        seq_with_breaks += sequence
        seq_with_breaks += '\n'
    return seq_with_breaks

def get_mean_and_st_dev_identity(alignments):
    '''
    This function looks at all alignments and specifically examines the ones where the alignment
    is in the middle of a reference and did not have to be artificially extended (i.e. the
    alignment was complete out of GraphMap). It then returns the mean and standard deviation for
    the identities of these alignments.
    '''
    identities = []
    for alignment in alignments:
        if alignment.read_start_pos == 0 or alignment.read_end_pos == alignment.read_length:
            continue
        if alignment.extended:
            continue
        identities.append(alignment.percent_identity)
    num = len(identities)
    if not num:
        return 0.0, 0.0
    mean = sum(identities) / num
    st_dev = 0.0
    if num > 1:
        sum_squares = sum((x - mean) ** 2 for x in identities)
        st_dev = (sum_squares / (num - 1)) ** 0.5
    return mean, st_dev









class LongRead(object):
    '''
    This class holds a long read, e.g. from PacBio or Oxford Nanopore.
    '''
    def __init__(self, name, sequence, qualities):
        self.name = name
        self.sequence = sequence
        self.qualities = qualities
        self.alignments = []

    def remove_conflicting_alignments(self):
        '''
        This function removes alignments from the read which are likely to be spurious. It sorts
        alignments by identity and works through them from highest identity to lowest identity,
        only keeping alignments that cover new parts of the read.
        It also uses an identity threshold to remove alignments with very poor identity.
        '''
        self.alignments = sorted(self.alignments, reverse=True,
                                 key=lambda x: (x.percent_identity, random.random()))
        kept_alignments = []
        read_ranges = []
        for alignment in self.alignments:
            read_range = alignment.read_start_end_positive_strand()
            if not range_is_contained(read_range, read_ranges):
                read_ranges.append(read_range)
                read_ranges = simplify_ranges(read_ranges)
                kept_alignments.append(alignment)
        self.alignments = kept_alignments

    def remove_low_id_alignments(self, id_threshold):
        '''
        This function removes alignments with identity below the cutoff.
        '''
        self.alignments = [x for x in self.alignments if x.percent_identity >= id_threshold]

    def get_fastq(self):
        '''
        Returns a string for the read in FASTQ format. It contains four lines and ends in a line
        break.
        '''
        return '@' + self.name + '\n' + \
               self.sequence + '\n' + \
               '+' + self.name + '\n' + \
               self.qualities + '\n'

    def get_descriptive_string(self):
        '''
        Returns a multi-line string that describes the read and its alignments.
        '''
        header = self.name + ' (' + str(len(self.sequence)) + ' bp)'
        line = '-' * len(header)
        description = header + '\n' + line + '\n'
        if not self.alignments:
            description += 'no alignments'
        else:
            description += '%.2f' % (100.0 * self.get_fraction_aligned()) + '% aligned\n'
            description += '\n'.join([str(x) for x in self.alignments])
        return description + '\n\n'

    def get_fraction_aligned(self):
        '''
        This function returns the fraction of the read which is covered by any of the read's
        alignments.
        '''
        read_ranges = [x.read_start_end_positive_strand() for x in self.alignments]
        read_ranges = simplify_ranges(read_ranges)
        aligned_length = sum([x[1] - x[0] for x in read_ranges])
        return aligned_length / len(self.sequence)



class Alignment(object):
    '''
    This class describes an alignment between a long read and a contig.
    '''
    def __init__(self, sam_line, references):

        # Load all important parts from the SAM line.
        sam_parts = sam_line.split('\t')
        self.read_name = sam_parts[0].split('/')[0]
        self.flag = int(sam_parts[1])
        self.reverse_complement = bool(self.flag & 0x10)
        self.ref_name = sam_parts[2]
        self.mapping_quality = int(sam_parts[4])
        self.cigar = sam_parts[5]
        self.cigar_parts = re.findall(r'\d+\w', self.cigar)
        self.full_read_sequence = sam_parts[9]
        self.read_length = len(self.full_read_sequence)
        self.read_quality = sam_parts[10]
        self.flags = sam_parts[11:]

        # Determine the position of the alignment in the reference.
        self.reference_length = len(references[self.ref_name])
        self.ref_start_pos = int(sam_parts[3]) - 1
        self.ref_end_pos = self.ref_start_pos
        for cigar_part in self.cigar_parts:
            self.ref_end_pos += get_ref_shift_from_cigar_part(cigar_part)
        self.reference_end_gap = self.reference_length - self.ref_end_pos

        # Determine the position of the alignment in the read.
        self.read_start_pos = self.get_start_soft_clips()
        self.read_end_pos = self.read_length - self.get_end_soft_clips()
        self.read_end_gap = self.get_end_soft_clips()

        # Extend the alignment so it is fully semi-global, reaching the end of the sequence.
        self.extended = False
        self.extend_alignment()

        # Get the aligned parts of the read and reference sequences.
        self.aligned_read_seq = self.full_read_sequence[self.read_start_pos:self.read_end_pos]
        self.aligned_ref_seq = references[self.ref_name][self.ref_start_pos:self.ref_end_pos]

        # Count matches, mismatches, insertions and deletions.
        # Insertions and deletions are counted per base. E.g. 5M3I4M has 3 insertions, not 1.
        self.matches = 0
        self.mismatches = 0
        self.insertions = 0
        self.deletions = 0
        self.percent_identity = 0.0
        self.tally_up_alignment()

    def __repr__(self):
        if self.reverse_complement:
            strand = '-'
        else:
            strand = '+'
        read_start, read_end = self.read_start_end_positive_strand()
        return self.read_name + ' (' + str(read_start) + '-' + str(read_end) + \
               ', strand: ' + strand + '), ' + self.ref_name + ' (' + \
               str(self.ref_start_pos) + '-' + str(self.ref_end_pos) + '), ' + \
               '%.2f' % self.percent_identity + '%'

    def get_alignment_length_read(self):
        '''
        Returns the length of the aligned read sequence.
        '''
        return self.read_end_pos - self.read_start_pos

    def get_alignment_length_reference(self):
        '''
        Returns the length of the aligned reference sequence.
        '''
        return self.ref_end_pos - self.ref_start_pos

    def get_read_to_ref_ratio(self):
        '''
        Returns the length ratio between the aligned parts of the read and reference.
        '''
        return self.get_alignment_length_read() / self.get_alignment_length_reference()

    def read_start_end_positive_strand(self):
        '''
        This function returns the read start/end coordinates for the positive strand of the read.
        For alignments on the positive strand, this is just the normal start/end. But for
        alignments on the negative strand, the coordinates are flipped to the other side.
        '''
        if not self.reverse_complement:
            return self.read_start_pos, self.read_end_pos
        else:
            start = self.read_length - self.read_end_pos
            end = self.read_length - self.read_start_pos
            return start, end

    def extend_alignment(self):
        '''
        This function extends the alignment as much as possible in both directions so the alignment
        only terminates when it reaches the end of either the read or the reference.
        It does not actually perform the alignment - it just counts each alignment as a match. This
        means that very long extensions will probably result in terrible alignments, but that's
        okay because we'll filter alignments by quality later.
        '''
        missing_bases_at_start = min(self.read_start_pos, self.ref_start_pos)
        missing_bases_at_end = min(self.read_end_gap, self.reference_end_gap)

        if missing_bases_at_start:
            self.extended = True

            # Adjust the start of the reference.
            self.ref_start_pos -= missing_bases_at_start

            # Adjust the start of the read and fix up the CIGAR to match.
            self.read_start_pos -= missing_bases_at_start
            self.cigar_parts.pop(0)
            if self.cigar_parts[0][-1] == 'M':
                new_match_length = missing_bases_at_start + int(self.cigar_parts[0][:-1])
                self.cigar_parts.pop(0)
                new_cigar_part = str(new_match_length) + 'M'
            else:
                new_cigar_part = str(missing_bases_at_start) + 'M'
            self.cigar_parts.insert(0, new_cigar_part)
            if self.read_start_pos > 0:
                self.cigar_parts.insert(0, str(self.read_start_pos) + 'S')
            self.cigar = ''.join(self.cigar_parts)

        if missing_bases_at_end:
            self.extended = True

            # Adjust the end of the reference.
            self.ref_end_pos += missing_bases_at_end
            self.reference_end_gap -= missing_bases_at_end

            # Adjust the end of the read and fix up the CIGAR to match.
            self.read_end_pos += missing_bases_at_end
            self.read_end_gap -= missing_bases_at_end
            self.cigar_parts.pop()
            if self.cigar_parts[-1][-1] == 'M':
                new_match_length = missing_bases_at_end + int(self.cigar_parts[-1][:-1])
                self.cigar_parts.pop()
                new_cigar_part = str(new_match_length) + 'M'
            else:
                new_cigar_part = str(missing_bases_at_end) + 'M'
            self.cigar_parts.append(new_cigar_part)
            if self.read_end_gap > 0:
                self.cigar_parts.append(str(self.read_end_gap) + 'S')
            self.cigar = ''.join(self.cigar_parts)

    def get_start_soft_clips(self):
        '''
        Returns the number of soft-clipped bases at the start of the alignment.
        '''
        match = re.search(r'^\d+S', self.cigar)
        if not match:
            return 0
        else:
            return int(match.group(0)[:-1])

    def get_end_soft_clips(self):
        '''
        Returns the number of soft-clipped bases at the start of the alignment.
        '''
        match = re.search(r'\d+S$', self.cigar)
        if not match:
            return 0
        else:
            return int(match.group(0)[:-1])

    def tally_up_alignment(self):
        '''
        Counts the matches, mismatches, indels and deletions. Also calculates the percent identity,
        which it does like BLAST: matches / alignment positions.
        '''
        # Reset any existing tallies.
        self.matches = 0
        self.mismatches = 0
        self.insertions = 0
        self.deletions = 0
        self.percent_identity = 0.0

        # Remove the soft clipping parts of the CIGAR string.
        cigar_parts = self.cigar_parts[:]
        if cigar_parts[0][-1] == 'S':
            cigar_parts.pop(0)
        if cigar_parts[-1][-1] == 'S':
            cigar_parts.pop()

        # Step through the alignment, counting as we go.
        read_i = 0
        ref_i = 0
        align_i = 0
        for cigar_part in cigar_parts:
            cigar_count = int(cigar_part[:-1])
            cigar_type = cigar_part[-1]
            if cigar_type == 'I':
                self.insertions += cigar_count
                read_i += cigar_count
            elif cigar_type == 'D':
                self.deletions += cigar_count
                ref_i += cigar_count
            else: # match/mismatch
                for _ in range(cigar_count):
                    read_base = self.aligned_read_seq[read_i]
                    ref_base = self.aligned_ref_seq[ref_i]
                    if read_base == ref_base:
                        self.matches += 1
                    else:
                        self.mismatches += 1
                    read_i += 1
                    ref_i += 1
            align_i += cigar_count
        self.percent_identity = 100.0 * self.matches / align_i

    def get_sam_line(self):
        '''
        Returns a SAM alignment line.
        '''
        edit_distance = self.mismatches + self.insertions + self.deletions
        return '\t'.join([self.read_name, str(self.flag), self.ref_name,
                          str(self.ref_start_pos + 1), str(self.mapping_quality), self.cigar,
                          '*', '0', '0', self.full_read_sequence, self.read_quality,
                          'NM:i:' + str(edit_distance)])






if __name__ == '__main__':
    main()


